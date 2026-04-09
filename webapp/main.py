import os
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import requests
from azure.identity import AzureCliCredential, InteractiveBrowserCredential
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from msal import ConfidentialClientApplication
from pydantic import BaseModel
from scripts.fabric_publish import (
    FabricClient as PublishFabricClient,
    build_environment_definition,
    build_notebook_definition,
)
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

# Keep bearer tokens server-side to avoid oversized cookie sessions.
TOKEN_STORE: Dict[str, str] = {}
FABRIC_STATE_PATH = ROOT / "data" / "reports" / "fabric_workspace_state.json"
PURVIEW_STATE_PATH = ROOT / "data" / "reports" / "purview_selection_state.json"
FABRIC_API_BASE = "https://api.fabric.microsoft.com/v1"

class StepRunRequest(BaseModel):
    step_id: str
    subscription_id: str
    key_vault_id: str
    key_vault_name: str


class PurviewSelectionRequest(BaseModel):
    primary_account_name: str


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


def _msal_env_configured() -> bool:
    required = ["WEBAPP_CLIENT_ID", "WEBAPP_CLIENT_SECRET", "AZURE_TENANT_ID"]
    return all(bool(os.getenv(name)) for name in required)


def _slugify_workspace_name(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9-]+", "-", value).strip("-")
    return slug or "PurviewAuditWorkspace"


def _desired_workspace_name(first_run: bool) -> str:
    base = _slugify_workspace_name(os.getenv("FABRIC_WORKSPACE_NAME", "PurviewAuditWorkspace"))
    if first_run and not os.getenv("FABRIC_WORKSPACE_ID"):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        return f"{base}-{stamp}"
    return base


def _read_fabric_state() -> Optional[Dict[str, Any]]:
    if not FABRIC_STATE_PATH.exists():
        return None
    try:
        return json.loads(FABRIC_STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _write_fabric_state(state: Dict[str, Any]) -> None:
    FABRIC_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FABRIC_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _read_purview_state() -> Optional[Dict[str, Any]]:
    if not PURVIEW_STATE_PATH.exists():
        return None
    try:
        return json.loads(PURVIEW_STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _write_purview_state(state: Dict[str, Any]) -> None:
    PURVIEW_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PURVIEW_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _fabric_token() -> str:
    tenant_id = os.getenv("AZURE_TENANT_ID") or None
    scope = "https://api.fabric.microsoft.com/.default"

    try:
        cli_cred = AzureCliCredential(tenant_id=tenant_id)
        return cli_cred.get_token(scope).token
    except Exception as exc:
        logger.info("Azure CLI Fabric token unavailable: %s", exc)

    try:
        browser_cred = InteractiveBrowserCredential(tenant_id=tenant_id)
        return browser_cred.get_token(scope).token
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Could not acquire Fabric API token. Sign in with Azure CLI or interactive browser first.",
        ) from exc


class _FabricApiClient:
    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
        )

    def _request(self, method: str, path: str, expected: tuple[int, ...] = (200, 201), **kwargs: Any) -> requests.Response:
        url = path if path.startswith("http") else f"{FABRIC_API_BASE}{path}"
        response = self.session.request(method, url, timeout=60, **kwargs)
        if response.status_code not in expected:
            detail = response.text.strip()
            raise HTTPException(status_code=502, detail=f"Fabric API error {response.status_code}: {detail}")
        return response

    def list_workspaces(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        path: Optional[str] = "/workspaces"
        while path:
            response = self._request("GET", path, expected=(200,))
            payload = response.json()
            items.extend(payload.get("value", []))
            path = payload.get("continuationUri")
        return items

    def get_workspace_by_id(self, workspace_id: str) -> Optional[Dict[str, Any]]:
        for ws in self.list_workspaces():
            if ws.get("id") == workspace_id:
                return ws
        return None

    def get_workspace_by_name(self, workspace_name: str) -> Optional[Dict[str, Any]]:
        for ws in self.list_workspaces():
            if ws.get("displayName") == workspace_name:
                return ws
        return None

    def create_workspace(self, workspace_name: str, description: str, capacity_id: Optional[str] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "displayName": workspace_name,
            "description": description,
        }
        if capacity_id:
            payload["capacityId"] = capacity_id
        response = self._request("POST", "/workspaces", expected=(201,), json=payload)
        return response.json()


def _ensure_fabric_workspace() -> Dict[str, Any]:
    token = _fabric_token()
    client = _FabricApiClient(token)

    state = _read_fabric_state()
    if state and state.get("workspace_id"):
        existing = client.get_workspace_by_id(state["workspace_id"])
        if existing:
            state["workspace_name"] = existing.get("displayName", state.get("workspace_name", ""))
            state["status"] = "REUSED"
            state["last_used_utc"] = datetime.now(timezone.utc).isoformat()
            _write_fabric_state(state)
            return state

    configured_workspace_id = os.getenv("FABRIC_WORKSPACE_ID", "").strip()
    if configured_workspace_id:
        existing = client.get_workspace_by_id(configured_workspace_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Configured FABRIC_WORKSPACE_ID not found: {configured_workspace_id}")
        state = {
            "workspace_id": existing.get("id", configured_workspace_id),
            "workspace_name": existing.get("displayName", _desired_workspace_name(first_run=False)),
            "status": "ATTACHED",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "last_used_utc": datetime.now(timezone.utc).isoformat(),
            "source": "env",
        }
        _write_fabric_state(state)
        return state

    workspace_name = _desired_workspace_name(first_run=state is None)
    existing = client.get_workspace_by_name(workspace_name)
    status = "REUSED"
    if not existing:
        existing = client.create_workspace(
            workspace_name,
            description="Purview governance audit workspace",
            capacity_id=os.getenv("FABRIC_CAPACITY_ID", "").strip() or None,
        )
        status = "CREATED"

    result = {
        "workspace_id": existing.get("id", ""),
        "workspace_name": existing.get("displayName", workspace_name),
        "status": status,
        "created_utc": (state or {}).get("created_utc") or datetime.now(timezone.utc).isoformat(),
        "last_used_utc": datetime.now(timezone.utc).isoformat(),
        "source": "webapp",
    }
    _write_fabric_state(result)
    return result


def _bootstrap_fabric_assets(workspace_id: str) -> Dict[str, Any]:
    token = _fabric_token()
    client = PublishFabricClient(token)

    env_name = os.getenv("FABRIC_ENVIRONMENT_NAME", "PurviewAuditSpark")
    env_description = "Spark environment for Purview governance audit notebooks"
    env_definition_file = ROOT / "fabric" / "environment.yml"
    spark_settings_file = ROOT / "fabric" / "Sparkcompute.yml"

    if not env_definition_file.exists() or not spark_settings_file.exists():
        raise HTTPException(status_code=500, detail="Fabric environment definition files are missing in fabric/.")

    environment = client.find_item_by_name(workspace_id, "Environment", env_name)
    env_status = "REUSED"
    if not environment:
        definition = build_environment_definition(env_definition_file, spark_settings_file, env_name, env_description)
        environment = client.create_environment(workspace_id, env_name, env_description, definition)
        env_status = "CREATED"

    environment_id = environment.get("id") if isinstance(environment, dict) else None
    if environment_id:
        client.publish_environment(workspace_id, environment_id)

    notebook_results: List[Dict[str, str]] = []
    for notebook_name in [item["notebook"] for item in STEP_DEFINITIONS]:
        notebook_path = ROOT / "notebooks" / notebook_name
        if not notebook_path.exists():
            notebook_results.append({"name": notebook_name, "status": "MISSING"})
            continue

        display_name = notebook_path.stem
        existing = client.find_item_by_name(workspace_id, "Notebook", display_name)
        if existing:
            notebook_results.append({"name": display_name, "status": "REUSED"})
            continue

        definition = build_notebook_definition(notebook_path, display_name, f"Provisioned notebook: {display_name}")
        client.create_notebook(workspace_id, display_name, f"Provisioned notebook: {display_name}", definition)
        notebook_results.append({"name": display_name, "status": "CREATED"})

    return {
        "environment": {
            "name": env_name,
            "status": env_status,
            "id": environment_id or "",
        },
        "notebooks": notebook_results,
    }


def _fallback_interactive_login(request: Request) -> RedirectResponse:
    tenant_id = os.getenv("AZURE_TENANT_ID") or None
    access_token: Optional[str] = None

    try:
        credential = AzureCliCredential(tenant_id=tenant_id)
        access_token = credential.get_token("https://management.azure.com/.default").token
    except Exception as exc:
        logger.info("Azure CLI auth unavailable, attempting interactive browser credential: %s", exc)

    if not access_token:
        try:
            browser_credential = InteractiveBrowserCredential(tenant_id=tenant_id)
            access_token = browser_credential.get_token("https://management.azure.com/.default").token
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Interactive sign-in is unavailable. Install Azure CLI and run 'az login', or configure WEBAPP_CLIENT_ID/WEBAPP_CLIENT_SECRET."
                ),
            ) from exc

    _store_access_token(request, access_token)
    request.session["user_claims"] = {
        "tid": tenant_id or "",
        "name": "Azure CLI Authenticated User",
        "preferred_username": "azure-cli",
    }
    return RedirectResponse("/")


def _redirect_uri(request: Request) -> str:
    configured = os.getenv("WEBAPP_REDIRECT_URI")
    if configured:
        return configured
    return str(request.url_for("auth_callback"))


def _store_access_token(request: Request, token: str) -> None:
    token_ref = request.session.get("token_ref") or str(uuid4())
    request.session["token_ref"] = token_ref
    TOKEN_STORE[token_ref] = token
    request.session.pop("access_token", None)


def _access_token(request: Request) -> str:
    token_ref = request.session.get("token_ref")
    token = TOKEN_STORE.get(token_ref, "") if token_ref else ""
    if not token:
        # Backward compatibility for older cookie sessions.
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


def _list_purview_accounts(token: str, subscription_ids: List[str]) -> List[Dict[str, Any]]:
    accounts: List[Dict[str, Any]] = []
    for subscription_id in subscription_ids:
        try:
            response = requests.get(
                f"https://management.azure.com/subscriptions/{subscription_id}/providers/Microsoft.Purview/accounts?api-version=2021-12-01",
                headers=_headers(token),
                timeout=30,
            )
            if response.status_code == 200:
                for account in response.json().get("value", []):
                    account_id = account.get("id", "")
                    accounts.append(
                        {
                            "id": account_id,
                            "name": account.get("name", ""),
                            "subscription_id": subscription_id,
                            "resource_group": (account_id.split("/")[4] if "/resourceGroups/" in account_id else ""),
                            "location": account.get("location", ""),
                        }
                    )
            else:
                logger.warning("Purview account lookup failed for %s: %s %s", subscription_id, response.status_code, response.text)
        except requests.RequestException as exc:
            logger.warning("Purview account lookup request failed for %s: %s", subscription_id, exc)
    return accounts


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


def _fabric_workspace_context() -> Dict[str, Any]:
    state = _read_fabric_state()
    if not state:
        return {
            "configured": False,
            "workspace_id": "",
            "workspace_name": "",
            "status": "NOT_CONFIGURED",
        }

    return {
        "configured": bool(state.get("workspace_id")),
        "workspace_id": state.get("workspace_id", ""),
        "workspace_name": state.get("workspace_name", ""),
        "status": state.get("status", "REUSED"),
        "created_utc": state.get("created_utc"),
        "last_used_utc": state.get("last_used_utc"),
    }


def _purview_selection_context(discovered_accounts: List[Dict[str, Any]]) -> Dict[str, Any]:
    state = _read_purview_state() or {}
    primary_name = state.get("primary_account_name", "")
    if primary_name and not any(item.get("name") == primary_name for item in discovered_accounts):
        primary_name = ""

    return {
        "accounts": discovered_accounts,
        "primary_account_name": primary_name,
        "configured": bool(primary_name),
    }


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
    if not _msal_env_configured():
        return _fallback_interactive_login(request)

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

    _store_access_token(request, result["access_token"])
    request.session["user_claims"] = result.get("id_token_claims", {})
    return RedirectResponse("/")


@app.get("/auth/logout")
def auth_logout(request: Request):
    token_ref = request.session.get("token_ref")
    if token_ref:
        TOKEN_STORE.pop(token_ref, None)
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
        purview_accounts = _list_purview_accounts(token, subscription_ids)
        steps = [_step_payload(step) for step in STEP_DEFINITIONS]
    except Exception as exc:
        logger.exception("Failed to load Azure context")
        raise HTTPException(status_code=502, detail=f"Could not load Azure context: {exc}") from exc

    return JSONResponse(
        {
            "tenant": tenant,
            "subscriptions": subscriptions,
            "key_vaults": key_vaults,
            "purview": _purview_selection_context(purview_accounts),
            "steps": steps,
            "fabric_workspace": _fabric_workspace_context(),
            "summary": {
                "subscription_count": len(subscriptions),
                "key_vault_count": len(key_vaults),
                "purview_account_count": len(purview_accounts),
            },
        }
    )


@app.post("/api/purview/selection")
def api_set_purview_selection(request: Request, payload: PurviewSelectionRequest):
    token = _access_token(request)
    subscriptions = _list_subscriptions(token)
    subscription_ids = [sub.get("subscriptionId") for sub in subscriptions if sub.get("subscriptionId")]
    discovered_accounts = _list_purview_accounts(token, subscription_ids)

    if not any(item.get("name") == payload.primary_account_name for item in discovered_accounts):
        raise HTTPException(status_code=400, detail=f"Primary Purview account not found: {payload.primary_account_name}")

    state = {
        "primary_account_name": payload.primary_account_name,
        "updated_utc": datetime.now(timezone.utc).isoformat(),
    }
    _write_purview_state(state)
    return JSONResponse({"purview": _purview_selection_context(discovered_accounts)})


@app.post("/api/fabric/workspace/ensure")
def api_ensure_fabric_workspace(request: Request):
    _access_token(request)
    workspace_state = _ensure_fabric_workspace()
    bootstrap = _bootstrap_fabric_assets(workspace_state.get("workspace_id", ""))
    return JSONResponse({
        "fabric_workspace": _fabric_workspace_context(),
        "workspace_result": workspace_state,
        "bootstrap": bootstrap,
    })


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

    fabric_workspace = _fabric_workspace_context()
    if not fabric_workspace.get("configured"):
        raise HTTPException(status_code=400, detail="Fabric workspace is not configured. Run 'Ensure Fabric Workspace' first.")

    artifact = _artifact_status(step["artifact"])
    run_plan = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tenant": _tenant_summary(request.session.get("user_claims", {})),
        "selected_subscription_id": payload.subscription_id,
        "selected_key_vault": {
            "id": payload.key_vault_id,
            "name": payload.key_vault_name,
        },
        "fabric_workspace": fabric_workspace,
        "purview": _read_purview_state() or {},
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
            "prompt": f"Open and run {step['notebook']} now against Fabric workspace {fabric_workspace.get('workspace_name', '')} ({fabric_workspace.get('workspace_id', '')}). After it completes, click Run Step again to refresh status.",
            "run_plan_path": str(_run_plan_path()),
        }
    )
