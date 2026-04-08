import os
import json
import logging
from datetime import datetime, timezone
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

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)
logger = logging.getLogger(__name__)

ARM_SCOPE = "https://management.azure.com/user_impersonation"
AUTH_SCOPES = [
    ARM_SCOPE,
    "openid",
    "profile",
    "offline_access",
]

STEP_DEFINITIONS = [
    {
        "id": "step-1-setup",
        "title": "Run Setup and Discovery",
        "notebook": "00-Setup.ipynb",
        "artifact": ROOT / "data" / "raw" / "setup_audit_config.json",
        "description": "Authenticate, discover Purview instances, and persist setup configuration.",
    },
    {
        "id": "step-2-purview-extract",
        "title": "Run Purview Extraction",
        "notebook": "01-Purview-Extract.ipynb",
        "artifact": ROOT / "data" / "raw" / "purview_extraction.json",
        "description": "Extract collections, sources, assets, scans, classifications, and runtimes.",
    },
    {
        "id": "step-3-catalog-extract",
        "title": "Run Unified Catalog Extraction",
        "notebook": "02-UnifiedCatalog-Extract.ipynb",
        "artifact": ROOT / "data" / "raw" / "unified_catalog_extraction.json",
        "description": "Extract data products, catalog assets, domains, and quality scores.",
    },
    {
        "id": "step-4-transform",
        "title": "Run Transform and Normalize",
        "notebook": "03-Transform-Data.ipynb",
        "artifact": ROOT / "data" / "reports" / "transform_summary.json",
        "description": "Generate curated dimensions, facts, and relationship graph outputs.",
    },
    {
        "id": "step-5-keyvault-validation",
        "title": "Run Key Vault Validation",
        "notebook": "04-KeyVault-Validation.ipynb",
        "artifact": ROOT / "data" / "reports" / "key_vault_connectivity.json",
        "description": "Validate vault access and record remediation guidance.",
    },
    {
        "id": "step-6-load",
        "title": "Run Final Load",
        "notebook": "05-Load-Fabric.ipynb",
        "artifact": ROOT / "data" / "reports" / "load_manifest.json",
        "description": "Publish curated datasets and generate reporting manifests.",
    },
]

app = FastAPI(title="Purview Fabric Provisioning")
app.add_middleware(SessionMiddleware, secret_key=os.getenv("WEBAPP_SESSION_SECRET", "local-dev-change-me"))
app.mount("/static", StaticFiles(directory=ROOT / "webapp" / "static"), name="static")
templates = Jinja2Templates(directory=str(ROOT / "webapp" / "templates"))

class StepRunRequest(BaseModel):
    step_id: str
    subscription_id: str
    key_vault_id: str
    key_vault_name: str


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


def _headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _tenant_summary(claims: Dict[str, Any]) -> Dict[str, str]:
    return {
        "tenant_id": claims.get("tid", ""),
        "user_name": claims.get("name", ""),
        "upn": claims.get("preferred_username", ""),
    }


def _list_subscriptions(token: str) -> List[Dict[str, Any]]:
    try:
        response = requests.get(
            "https://management.azure.com/subscriptions?api-version=2020-01-01",
            headers=_headers(token),
            timeout=30,
        )
        if response.status_code == 200:
            payload = response.json()
            return payload.get("value", [])
        logger.warning("Subscription lookup returned %s: %s", response.status_code, response.text)
    except requests.RequestException as exc:
        logger.warning("Subscription lookup failed: %s", exc)
    return []


def _list_key_vaults(token: str, subscription_ids: List[str]) -> List[Dict[str, Any]]:
    all_vaults: List[Dict[str, Any]] = []
    for subscription_id in subscription_ids:
        try:
            response = requests.get(
                f"https://management.azure.com/subscriptions/{subscription_id}/providers/Microsoft.KeyVault/vaults?api-version=2023-07-01",
                headers=_headers(token),
                timeout=30,
            )
            if response.status_code == 200:
                for vault in response.json().get("value", []):
                    props = vault.get("properties", {})
                    all_vaults.append(
                        {
                            "id": vault.get("id", ""),
                            "name": vault.get("name", ""),
                            "subscription_id": subscription_id,
                            "resource_group": (vault.get("id", "").split("/")[4] if "/resourceGroups/" in vault.get("id", "") else ""),
                            "location": vault.get("location", ""),
                            "vault_uri": props.get("vaultUri", ""),
                        }
                    )
            else:
                logger.warning("Key Vault lookup failed for %s: %s %s", subscription_id, response.status_code, response.text)
        except requests.RequestException as exc:
            logger.warning("Key Vault lookup request failed for %s: %s", subscription_id, exc)
    return all_vaults


def _artifact_status(path: Path) -> Dict[str, Any]:
    return {
        "exists": path.exists(),
        "path": str(path),
        "last_modified": path.stat().st_mtime if path.exists() else None,
    }


def _step_payload(step: Dict[str, Any]) -> Dict[str, Any]:
    artifact = _artifact_status(step["artifact"])
    return {
        "id": step["id"],
        "title": step["title"],
        "description": step["description"],
        "notebook": step["notebook"],
        "artifact": artifact,
        "status": "COMPLETE" if artifact["exists"] else "PENDING",
        "prompt": f"Run {step['notebook']} and come back to mark this step complete.",
    }


def _run_plan_path() -> Path:
    reports_dir = ROOT / "data" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    return reports_dir / "webapp_run_plan.json"


def _write_run_plan(payload: Dict[str, Any]) -> None:
    plan_path = _run_plan_path()
    with plan_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


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
        scopes=AUTH_SCOPES,
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

    try:
        subscriptions = _list_subscriptions(token)
        subscription_ids = [sub.get("subscriptionId") for sub in subscriptions if sub.get("subscriptionId")]
        key_vaults = _list_key_vaults(token, subscription_ids)
        steps = [_step_payload(step) for step in STEP_DEFINITIONS]
    except Exception as exc:
        logger.exception("Failed to load Azure context")
        raise HTTPException(status_code=502, detail=f"Could not load Azure context: {exc}") from exc

    return JSONResponse(
        {
            "tenant": tenant,
            "subscriptions": subscriptions,
            "key_vaults": key_vaults,
            "steps": steps,
            "summary": {
                "subscription_count": len(subscriptions),
                "key_vault_count": len(key_vaults),
            },
        }
    )


@app.get("/api/steps")
def api_steps() -> JSONResponse:
    return JSONResponse({"steps": [_step_payload(step) for step in STEP_DEFINITIONS]})


@app.post("/api/steps/run")
def api_steps_run(request: Request, payload: StepRunRequest):
    _access_token(request)

    step = next((item for item in STEP_DEFINITIONS if item["id"] == payload.step_id), None)
    if step is None:
        raise HTTPException(status_code=400, detail=f"Unknown step_id: {payload.step_id}")

    if not payload.subscription_id:
        raise HTTPException(status_code=400, detail="subscription_id is required.")
    if not payload.key_vault_id or not payload.key_vault_name:
        raise HTTPException(status_code=400, detail="key_vault selection is required.")

    artifact = _artifact_status(step["artifact"])
    run_plan = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tenant": _tenant_summary(request.session.get("user_claims", {})),
        "selected_subscription_id": payload.subscription_id,
        "selected_key_vault": {
            "id": payload.key_vault_id,
            "name": payload.key_vault_name,
        },
        "current_step": {
            "id": step["id"],
            "title": step["title"],
            "notebook": step["notebook"],
            "artifact": artifact,
        },
        "steps": [_step_payload(item) for item in STEP_DEFINITIONS],
    }
    _write_run_plan(run_plan)

    status = "COMPLETE" if artifact["exists"] else "WAITING_FOR_NOTEBOOK_RUN"
    return JSONResponse(
        {
            "status": status,
            "step": _step_payload(step),
            "prompt": f"Open and run {step['notebook']} now. After it completes, click Run Step again to refresh status.",
            "run_plan_path": str(_run_plan_path()),
        }
    )
