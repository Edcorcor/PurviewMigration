import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests
import yaml
from azure.identity import AzureCliCredential, ClientSecretCredential, DefaultAzureCredential, DeviceCodeCredential, InteractiveBrowserCredential
from dotenv import load_dotenv

BASE_URL = "https://api.fabric.microsoft.com/v1"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NOTEBOOK = ROOT / "notebooks" / "00-Setup.ipynb"
DEFAULT_ENV_LIBS = ROOT / "fabric" / "environment.yml"
DEFAULT_SPARK_SETTINGS = ROOT / "fabric" / "Sparkcompute.yml"


class FabricPublishError(RuntimeError):
    pass


def load_configuration() -> Dict[str, Any]:
    load_dotenv(ROOT / ".env", override=False)

    config_path = ROOT / "config" / "environment.yml"
    config = {}
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as handle:
            config = yaml.safe_load(handle) or {}

    return config


def config_value(config: Dict[str, Any], dotted_key: str, env_name: Optional[str] = None, default: Any = None) -> Any:
    if env_name and os.getenv(env_name):
        return os.getenv(env_name)

    value = config
    for part in dotted_key.split("."):
        if not isinstance(value, dict) or part not in value:
            return default
        value = value[part]

    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        resolved_name = value[2:-1]
        return os.getenv(resolved_name, default)

    return value if value is not None else default


def encode_file(file_path: Path) -> str:
    return base64.b64encode(file_path.read_bytes()).decode("ascii")


def encode_text(payload: str) -> str:
    return base64.b64encode(payload.encode("utf-8")).decode("ascii")


def build_platform_metadata(item_type: str, display_name: str, description: str) -> str:
    payload = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {
            "type": item_type,
            "displayName": display_name,
            "description": description,
        },
    }
    return json.dumps(payload, separators=(",", ":"))


def get_access_token(config: Dict[str, Any]) -> str:
    tenant_id = config_value(config, "azure.tenant_id", "AZURE_TENANT_ID")
    if not tenant_id:
        raise FabricPublishError("AZURE_TENANT_ID is required.")

    client_id = os.getenv("AZURE_CLIENT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET")
    if client_id and client_secret:
        credential = ClientSecretCredential(tenant_id=tenant_id, client_id=client_id, client_secret=client_secret)
        return credential.get_token("https://api.fabric.microsoft.com/.default").token

    try:
        credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
        return credential.get_token("https://api.fabric.microsoft.com/.default").token
    except Exception:
        pass

    try:
        credential = AzureCliCredential(tenant_id=tenant_id)
        return credential.get_token("https://api.fabric.microsoft.com/.default").token
    except Exception:
        pass

    try:
        credential = InteractiveBrowserCredential(tenant_id=tenant_id)
        return credential.get_token("https://api.fabric.microsoft.com/.default").token
    except Exception:
        pass

    public_client_id = os.getenv("FABRIC_PUBLIC_CLIENT_ID")
    if not public_client_id:
        raise FabricPublishError(
            "Fabric publish requires delegated or app authentication. Tried environment credentials, Azure CLI, and interactive browser auth. "
            "Set FABRIC_PUBLIC_CLIENT_ID for device-code login, or AZURE_CLIENT_ID and AZURE_CLIENT_SECRET for service principal auth."
        )

    def prompt_callback(verification_uri: str, user_code: str, expires_on: Any) -> None:
        print("Open this URL in a browser and enter the code to authenticate Fabric API access:")
        print(f"  URL : {verification_uri}")
        print(f"  Code: {user_code}")
        print(f"  Expires: {expires_on}")

    credential = DeviceCodeCredential(
        tenant_id=tenant_id,
        client_id=public_client_id,
        prompt_callback=prompt_callback,
    )
    token = credential.get_token(
        "https://api.fabric.microsoft.com/Workspace.ReadWrite.All",
        "https://api.fabric.microsoft.com/Item.ReadWrite.All",
        "https://api.fabric.microsoft.com/Environment.ReadWrite.All",
    )
    return token.token


class FabricClient:
    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
        )

    def request(self, method: str, path: str, expected: tuple[int, ...] = (200, 201, 202), **kwargs: Any) -> requests.Response:
        url = path if path.startswith("http") else f"{BASE_URL}{path}"
        response = self.session.request(method, url, **kwargs)
        if response.status_code not in expected:
            details = response.text.strip()
            raise FabricPublishError(f"{method} {url} failed: {response.status_code} {details}")
        return response

    def poll_operation(self, location: str, timeout_seconds: int = 900) -> Optional[Dict[str, Any]]:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            response = self.request("GET", location, expected=(200, 201, 202))
            if response.status_code in (200, 201):
                return response.json() if response.text else None
            retry_after = int(response.headers.get("Retry-After", "15"))
            time.sleep(retry_after)
        raise FabricPublishError(f"Timed out waiting for Fabric operation: {location}")

    def list_all_workspaces(self) -> list[Dict[str, Any]]:
        workspaces = []
        path = "/workspaces"
        while path:
            response = self.request("GET", path)
            payload = response.json()
            workspaces.extend(payload.get("value", []))
            continuation_uri = payload.get("continuationUri")
            path = continuation_uri if continuation_uri else None
        return workspaces

    def find_workspace_by_name(self, display_name: str) -> Optional[Dict[str, Any]]:
        for workspace in self.list_all_workspaces():
            if workspace.get("displayName") == display_name:
                return workspace
        return None

    def create_workspace(self, display_name: str, description: str, capacity_id: Optional[str] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "displayName": display_name,
            "description": description,
        }
        if capacity_id:
            payload["capacityId"] = capacity_id
        response = self.request("POST", "/workspaces", json=payload, expected=(201,))
        return response.json()

    def list_items(self, workspace_id: str, item_type: Optional[str] = None) -> list[Dict[str, Any]]:
        items = []
        path = f"/workspaces/{workspace_id}/items"
        if item_type:
            path = f"{path}?type={item_type}"
        while path:
            response = self.request("GET", path)
            payload = response.json()
            items.extend(payload.get("value", []))
            continuation_uri = payload.get("continuationUri")
            path = continuation_uri if continuation_uri else None
        return items

    def find_item_by_name(self, workspace_id: str, item_type: str, display_name: str) -> Optional[Dict[str, Any]]:
        for item in self.list_items(workspace_id, item_type=item_type):
            if item.get("displayName") == display_name:
                return item
        return None

    def create_environment(self, workspace_id: str, display_name: str, description: str, definition: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "displayName": display_name,
            "description": description,
            "definition": definition,
        }
        response = self.request("POST", f"/workspaces/{workspace_id}/environments", json=payload)
        if response.status_code == 202:
            return self.poll_operation(response.headers["Location"]) or {}
        return response.json()

    def publish_environment(self, workspace_id: str, environment_id: str) -> Dict[str, Any]:
        response = self.request(
            "POST",
            f"/workspaces/{workspace_id}/environments/{environment_id}/staging/publish?beta=false",
            expected=(200, 202),
        )
        if response.status_code == 202:
            return self.poll_operation(response.headers["Location"]) or {}
        return response.json() if response.text else {}

    def create_notebook(self, workspace_id: str, display_name: str, description: str, definition: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "displayName": display_name,
            "description": description,
            "definition": definition,
        }
        response = self.request("POST", f"/workspaces/{workspace_id}/notebooks", json=payload)
        if response.status_code == 202:
            return self.poll_operation(response.headers["Location"]) or {}
        return response.json()


def build_environment_definition(env_file: Path, spark_settings_file: Path, display_name: str, description: str) -> Dict[str, Any]:
    return {
        "parts": [
            {
                "path": "Libraries/PublicLibraries/environment.yml",
                "payload": encode_file(env_file),
                "payloadType": "InlineBase64",
            },
            {
                "path": "Setting/Sparkcompute.yml",
                "payload": encode_file(spark_settings_file),
                "payloadType": "InlineBase64",
            },
            {
                "path": ".platform",
                "payload": encode_text(build_platform_metadata("Environment", display_name, description)),
                "payloadType": "InlineBase64",
            },
        ]
    }


def build_notebook_definition(notebook_path: Path, display_name: str, description: str) -> Dict[str, Any]:
    return {
        "format": "ipynb",
        "parts": [
            {
                "path": "artifact.content.ipynb",
                "payload": encode_file(notebook_path),
                "payloadType": "InlineBase64",
            },
            {
                "path": ".platform",
                "payload": encode_text(build_platform_metadata("Notebook", display_name, description)),
                "payloadType": "InlineBase64",
            },
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a Fabric workspace, Spark environment, and publish a notebook.")
    parser.add_argument("--workspace-name", default=None)
    parser.add_argument("--workspace-id", default=os.getenv("FABRIC_WORKSPACE_ID"))
    parser.add_argument("--workspace-description", default="Purview governance audit workspace")
    parser.add_argument("--capacity-id", default=os.getenv("FABRIC_CAPACITY_ID"))
    parser.add_argument("--environment-name", default=os.getenv("FABRIC_ENVIRONMENT_NAME", "PurviewAuditSpark"))
    parser.add_argument("--environment-description", default="Spark environment for Purview governance audit notebooks")
    parser.add_argument("--notebook-name", default=os.getenv("FABRIC_NOTEBOOK_NAME", "00-Setup"))
    parser.add_argument("--notebook-description", default="Purview governance setup and discovery notebook")
    parser.add_argument("--notebook-path", default=str(DEFAULT_NOTEBOOK))
    parser.add_argument("--env-definition", default=str(DEFAULT_ENV_LIBS))
    parser.add_argument("--spark-settings", default=str(DEFAULT_SPARK_SETTINGS))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_configuration()

    workspace_name = args.workspace_name or config_value(config, "fabric.workspace_name", "FABRIC_WORKSPACE_NAME", "PurviewAuditWorkspace")
    notebook_path = Path(args.notebook_path)
    env_file = Path(args.env_definition)
    spark_settings_file = Path(args.spark_settings)

    if not notebook_path.exists():
        raise FabricPublishError(f"Notebook file not found: {notebook_path}")
    if not env_file.exists():
        raise FabricPublishError(f"Environment definition not found: {env_file}")
    if not spark_settings_file.exists():
        raise FabricPublishError(f"Spark settings definition not found: {spark_settings_file}")

    token = get_access_token(config)
    client = FabricClient(token)

    workspace = None
    if args.workspace_id:
        workspace = {"id": args.workspace_id, "displayName": workspace_name}
    else:
        workspace = client.find_workspace_by_name(workspace_name)
        if workspace:
            print(f"Reusing Fabric workspace: {workspace['displayName']} ({workspace['id']})")
        else:
            print(f"Creating Fabric workspace: {workspace_name}")
            workspace = client.create_workspace(workspace_name, args.workspace_description, capacity_id=args.capacity_id)

    workspace_id = workspace["id"]

    environment = client.find_item_by_name(workspace_id, "Environment", args.environment_name)
    if environment:
        print(f"Reusing environment: {environment['displayName']} ({environment['id']})")
    else:
        print(f"Creating environment: {args.environment_name}")
        environment_definition = build_environment_definition(env_file, spark_settings_file, args.environment_name, args.environment_description)
        environment = client.create_environment(workspace_id, args.environment_name, args.environment_description, environment_definition)

    environment_id = environment.get("id")
    if environment_id:
        print(f"Publishing environment: {args.environment_name}")
        publish_result = client.publish_environment(workspace_id, environment_id)
        if publish_result:
            print(json.dumps(publish_result, indent=2))

    notebook = client.find_item_by_name(workspace_id, "Notebook", args.notebook_name)
    if notebook:
        print(f"Notebook already exists, skipping create: {notebook['displayName']} ({notebook['id']})")
    else:
        print(f"Publishing notebook: {args.notebook_name}")
        notebook_definition = build_notebook_definition(notebook_path, args.notebook_name, args.notebook_description)
        notebook = client.create_notebook(workspace_id, args.notebook_name, args.notebook_description, notebook_definition)

    print("Deployment complete.")
    print(json.dumps(
        {
            "workspace": workspace,
            "environment": environment,
            "notebook": notebook,
            "notebookPath": str(notebook_path),
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FabricPublishError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
