import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from msal import ConfidentialClientApplication
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from scripts.fabric_publish import (
    FabricClient,
    build_environment_definition,
    build_notebook_definition,
)

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)

NOTEBOOK_PATH = ROOT / "notebooks" / "00-Setup.ipynb"
ENV_FILE = ROOT / "fabric" / "environment.yml"
SPARK_SETTINGS_FILE = ROOT / "fabric" / "Sparkcompute.yml"

FABRIC_SCOPES = [
    "https://api.fabric.microsoft.com/Workspace.ReadWrite.All",
    "https://api.fabric.microsoft.com/Item.ReadWrite.All",
    "https://api.fabric.microsoft.com/Environment.ReadWrite.All",
    "https://api.powerbi.com/Capacity.Read.All",
    "openid",
    "profile",
    "offline_access",
]

app = FastAPI(title="Purview Fabric Provisioning")
app.add_middleware(SessionMiddleware, secret_key=os.getenv("WEBAPP_SESSION_SECRET", "local-dev-change-me"))
app.mount("/static", StaticFiles(directory=ROOT / "webapp" / "static"), name="static")
templates = Jinja2Templates(directory=str(ROOT / "webapp" / "templates"))


class ProvisionRequest(BaseModel):
    workspace_mode: str
    workspace_id: Optional[str] = None
    workspace_name: Optional[str] = None
    workspace_description: Optional[str] = "Purview governance audit workspace"
    capacity_id: Optional[str] = None
    environment_name: Optional[str] = "PurviewAuditSpark"
    environment_description: Optional[str] = "Spark environment for Purview governance audit notebooks"
    notebook_name: Optional[str] = "00-Setup"
    notebook_description: Optional[str] = "Purview governance setup and discovery notebook"


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise HTTPException(status_code=500, detail=f"Missing required environment variable: {name}")
    return value


def _build_msal_app() -> ConfidentialClientApplication:
    client_id = _required_env("WEBAPP_CLIENT_ID")
    client_secret = _required_env("WEBAPP_CLIENT_SECRET")
    tenant_id = _required_env("AZURE_TENANT_ID")
    authority = f"https://login.microsoftonline.com/{tenant_id}"

    return ConfidentialClientApplication(
        client_id=client_id,
        client_credential=client_secret,
        authority=authority,
    )


def _redirect_uri(request: Request) -> str:
    configured = os.getenv("WEBAPP_REDIRECT_URI")
    if configured:
        return configured
    return str(request.url_for("auth_callback"))


def _access_token(request: Request) -> str:
    token = request.session.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated. Sign in first.")
    return token


def _tenant_summary(claims: Dict[str, Any]) -> Dict[str, str]:
    return {
        "tenant_id": claims.get("tid", ""),
        "user_name": claims.get("name", ""),
        "upn": claims.get("preferred_username", ""),
    }


def _list_capacities(token: str) -> List[Dict[str, Any]]:
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get("https://api.powerbi.com/v1.0/myorg/capacities", headers=headers, timeout=30)
    if response.status_code == 200:
        payload = response.json()
        return payload.get("value", [])
    return []


@app.get("/")
def home(request: Request):
    user_claims = request.session.get("user_claims")
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "signed_in": bool(user_claims),
            "tenant": _tenant_summary(user_claims or {}),
            "workspace_name_default": os.getenv("FABRIC_WORKSPACE_NAME", "PurviewAuditWorkspace"),
            "environment_name_default": os.getenv("FABRIC_ENVIRONMENT_NAME", "PurviewAuditSpark"),
            "notebook_name_default": os.getenv("FABRIC_NOTEBOOK_NAME", "00-Setup"),
        },
    )


@app.get("/auth/login")
def auth_login(request: Request):
    msal_app = _build_msal_app()
    flow = msal_app.initiate_auth_code_flow(
        scopes=FABRIC_SCOPES,
        redirect_uri=_redirect_uri(request),
    )
    request.session["auth_flow"] = flow
    return RedirectResponse(flow["auth_uri"])


@app.get("/auth/callback", name="auth_callback")
def auth_callback(request: Request):
    msal_app = _build_msal_app()
    flow = request.session.get("auth_flow")
    if not flow:
        raise HTTPException(status_code=400, detail="Missing auth flow state.")

    query = dict(request.query_params)
    result = msal_app.acquire_token_by_auth_code_flow(flow, query)
    if "access_token" not in result:
        raise HTTPException(status_code=401, detail=result.get("error_description", "Sign-in failed."))

    request.session["access_token"] = result["access_token"]
    request.session["user_claims"] = result.get("id_token_claims", {})
    return RedirectResponse("/")


@app.get("/auth/logout")
def auth_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/")


@app.get("/api/context")
def api_context(request: Request):
    token = _access_token(request)
    tenant = _tenant_summary(request.session.get("user_claims", {}))

    fabric = FabricClient(token)
    workspaces = fabric.list_all_workspaces()
    capacities = _list_capacities(token)

    return JSONResponse(
        {
            "tenant": tenant,
            "workspaces": workspaces,
            "capacities": capacities,
        }
    )


@app.post("/api/provision")
def api_provision(request: Request, payload: ProvisionRequest):
    token = _access_token(request)
    fabric = FabricClient(token)

    workspace: Optional[Dict[str, Any]] = None
    if payload.workspace_mode == "existing":
        if not payload.workspace_id:
            raise HTTPException(status_code=400, detail="workspace_id is required when selecting existing workspace.")
        workspace = {"id": payload.workspace_id, "displayName": "Existing Workspace"}
    elif payload.workspace_mode == "create":
        if not payload.workspace_name:
            raise HTTPException(status_code=400, detail="workspace_name is required for workspace creation.")
        existing = fabric.find_workspace_by_name(payload.workspace_name)
        workspace = existing or fabric.create_workspace(
            payload.workspace_name,
            payload.workspace_description or "Purview governance audit workspace",
            capacity_id=payload.capacity_id,
        )
    else:
        raise HTTPException(status_code=400, detail="workspace_mode must be either 'existing' or 'create'.")

    workspace_id = workspace["id"]

    environment_name = payload.environment_name or "PurviewAuditSpark"
    existing_environment = fabric.find_item_by_name(workspace_id, "Environment", environment_name)
    if existing_environment:
        environment = existing_environment
    else:
        environment_def = build_environment_definition(
            ENV_FILE,
            SPARK_SETTINGS_FILE,
            environment_name,
            payload.environment_description or "Spark environment for Purview governance audit notebooks",
        )
        environment = fabric.create_environment(
            workspace_id,
            environment_name,
            payload.environment_description or "Spark environment for Purview governance audit notebooks",
            environment_def,
        )

    if environment.get("id"):
        fabric.publish_environment(workspace_id, environment["id"])

    notebook_name = payload.notebook_name or "00-Setup"
    existing_notebook = fabric.find_item_by_name(workspace_id, "Notebook", notebook_name)
    if existing_notebook:
        notebook = existing_notebook
    else:
        notebook_def = build_notebook_definition(
            NOTEBOOK_PATH,
            notebook_name,
            payload.notebook_description or "Purview governance setup and discovery notebook",
        )
        notebook = fabric.create_notebook(
            workspace_id,
            notebook_name,
            payload.notebook_description or "Purview governance setup and discovery notebook",
            notebook_def,
        )

    return JSONResponse(
        {
            "workspace": workspace,
            "environment": environment,
            "notebook": notebook,
            "message": "Provisioning complete.",
        }
    )
