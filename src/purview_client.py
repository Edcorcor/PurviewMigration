"""High-level client for Azure Purview discovery and metadata extraction."""

import json
import logging
import os
from typing import Dict, List, Any, Optional, Iterable
from urllib.parse import urlparse

import requests
from azure.identity import DefaultAzureCredential
from azure.mgmt.resourcegraph import ResourceGraphClient
from azure.mgmt.resourcegraph.models import QueryRequest


logger = logging.getLogger(__name__)


class PurviewClient:
    """Wrapper for Azure Purview APIs"""
    
    def __init__(self, credential=None):
        """
        Initialize Purview client
        
        Args:
            credential: Azure credential object (defaults to DefaultAzureCredential)
        """
        self.credential = credential or DefaultAzureCredential()
        self.base_url = None
        self.scan_base_url = None
        self.subscription_id = None
        self.session = requests.Session()
    
    def set_account(self, account_url: str):
        """Set the Purview account to query"""
        base_url = account_url.rstrip("/")
        self.base_url = base_url

        hostname = urlparse(base_url).hostname or ""
        account_name = hostname.split(".")[0]
        if account_name:
            self.scan_base_url = f"https://{account_name}.scan.purview.azure.com"

    def _get_headers(self, scope: str) -> Dict[str, str]:
        token = self.credential.get_token(scope).token
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _load_fixture(self, fixture_name: str) -> Optional[Any]:
        env_name = f"PURVIEW_{fixture_name.upper()}_FILE"
        fixture_path = os.getenv(env_name)
        if not fixture_path:
            return None

        try:
            with open(fixture_path, "r", encoding="utf-8") as handle:
                logger.info("Loading Purview fixture from %s", fixture_path)
                return json.load(handle)
        except Exception as exc:
            logger.warning("Could not load Purview fixture %s: %s", fixture_path, exc)
            return None

    @staticmethod
    def _extract_items(payload: Any, keys: Iterable[str] = ("value", "items", "entities", "data")) -> List[Dict[str, Any]]:
        if payload is None:
            return []
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in keys:
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
            return [payload]
        return []

    @staticmethod
    def _as_mapping(items: List[Dict[str, Any]], key_candidates: Iterable[str]) -> Dict[str, Dict[str, Any]]:
        mapped: Dict[str, Dict[str, Any]] = {}
        for index, item in enumerate(items, start=1):
            key = None
            for candidate in key_candidates:
                value = item.get(candidate)
                if value:
                    key = str(value)
                    break
            if not key:
                key = f"item-{index}"
            mapped[key] = item
        return mapped

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        scope: str,
        base_url: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Optional[Any]:
        root = (base_url or self.base_url or "").rstrip("/")
        if not root:
            raise ValueError("Purview account URL has not been configured")

        url = f"{root}/{path.lstrip('/')}"
        response = self.session.request(
            method=method,
            url=url,
            headers=self._get_headers(scope),
            params=params,
            json=payload,
            timeout=30,
        )

        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise RuntimeError(f"Purview request failed: {response.status_code} {response.text}")
        if not response.text.strip():
            return {}
        return response.json()

    def _first_success(
        self,
        method: str,
        candidates: List[Dict[str, Any]],
        fixture_name: Optional[str] = None,
    ) -> Optional[Any]:
        fixture = self._load_fixture(fixture_name) if fixture_name else None
        if fixture is not None:
            return fixture

        last_error: Optional[Exception] = None
        for candidate in candidates:
            try:
                result = self._request_json(method=method, **candidate)
                if result is not None:
                    return result
            except Exception as exc:
                last_error = exc
                logger.debug("Purview endpoint attempt failed for %s: %s", candidate.get("path"), exc)

        if last_error is not None:
            logger.warning("No Purview endpoint succeeded for %s: %s", fixture_name or "request", last_error)
        return None
    
    @staticmethod
    def discover_purview_instances(subscription_id: str, credential=None) -> List[Dict[str, str]]:
        """
        Discover all Purview instances in a subscription
        
        Args:
            subscription_id: Azure subscription ID
            credential: Azure credential (defaults to DefaultAzureCredential)
            
        Returns:
            List of Purview instance info dicts with keys: name, id, resource_group
        """
        if credential is None:
            credential = DefaultAzureCredential()
        
        client = ResourceGraphClient(credential)
        
        # Query for all Purview accounts
        query = QueryRequest(
            subscriptions=[subscription_id],
            query="resources | where type == 'microsoft.purview/accounts'"
        )
        
        try:
            results = client.resources(query)
            instances = []
            
            for resource in results.data:
                instances.append({
                    "name": resource.get("name"),
                    "id": resource.get("id"),
                    "resource_group": resource.get("resourceGroup"),
                    "location": resource.get("location"),
                    "type": resource.get("type")
                })
            
            logger.info(f"Discovered {len(instances)} Purview instance(s)")
            return instances
        
        except Exception as e:
            logger.error(f"Error discovering Purview instances: {e}")
            return []
    
    def get_collections(self) -> Dict[str, Any]:
        """
        Fetch all Collections from Purview
        
        Returns:
            Dictionary of collections keyed by ID
        """
        logger.info("Fetching Collections from Purview")
        payload = self._first_success(
            "GET",
            [
                {
                    "path": "/account/collections",
                    "scope": "https://purview.azure.net/.default",
                    "params": {"api-version": "2019-11-01-preview"},
                },
                {
                    "path": "/collections",
                    "scope": "https://purview.azure.net/.default",
                    "params": {"api-version": "2019-11-01-preview"},
                },
            ],
            fixture_name="collections",
        )
        return self._as_mapping(self._extract_items(payload), ("name", "id", "friendlyName"))
    
    def get_data_sources(self) -> Dict[str, Any]:
        """Fetch all Data Sources from Purview"""
        logger.info("Fetching Data Sources from Purview")
        payload = self._first_success(
            "GET",
            [
                {
                    "path": "/datasources",
                    "base_url": self.scan_base_url,
                    "scope": "https://purview.azure.net/.default",
                    "params": {"api-version": "2023-09-01-preview"},
                },
                {
                    "path": "/scan/datasources",
                    "base_url": self.scan_base_url,
                    "scope": "https://purview.azure.net/.default",
                    "params": {"api-version": "2023-09-01-preview"},
                },
            ],
            fixture_name="data_sources",
        )
        return self._as_mapping(self._extract_items(payload), ("id", "name"))
    
    def get_assets(self, filter: Optional[str] = None) -> Dict[str, Any]:
        """
        Fetch all cataloged Assets from Purview
        
        Args:
            filter: Optional filter expression
            
        Returns:
            Dictionary of assets
        """
        logger.info("Fetching Assets from Purview")

        fixture = self._load_fixture("assets")
        if fixture is not None:
            return self._as_mapping(self._extract_items(fixture), ("guid", "id", "qualifiedName", "name"))

        assets: List[Dict[str, Any]] = []
        offset = 0
        page_size = 100
        while True:
            payload = self._first_success(
                "POST",
                [
                    {
                        "path": "/catalog/api/atlas/v2/search/basic",
                        "scope": "https://purview.azure.net/.default",
                        "payload": {
                            "keywords": filter or "",
                            "limit": page_size,
                            "offset": offset,
                        },
                    }
                ],
            )
            page = self._extract_items(payload)
            if not page:
                break

            for entity in page:
                entity.setdefault("lineage", [])
                assets.append(entity)

            if len(page) < page_size:
                break
            offset += page_size

        return self._as_mapping(assets, ("guid", "id", "qualifiedName", "name"))
    
    def get_scans(self) -> Dict[str, Any]:
        """Fetch all Scan configurations from Purview"""
        logger.info("Fetching Scans from Purview")
        fixture = self._load_fixture("scans")
        if fixture is not None:
            return self._as_mapping(self._extract_items(fixture), ("id", "name"))

        scans: List[Dict[str, Any]] = []
        sources = self.get_data_sources()
        for source_id, source_data in sources.items():
            payload = self._first_success(
                "GET",
                [
                    {
                        "path": f"/datasources/{source_id}/scans",
                        "base_url": self.scan_base_url,
                        "scope": "https://purview.azure.net/.default",
                        "params": {"api-version": "2023-09-01-preview"},
                    },
                    {
                        "path": f"/scan/datasources/{source_id}/scans",
                        "base_url": self.scan_base_url,
                        "scope": "https://purview.azure.net/.default",
                        "params": {"api-version": "2023-09-01-preview"},
                    },
                ],
            )
            for scan in self._extract_items(payload):
                scan.setdefault("dataSourceId", source_id)
                scan.setdefault("dataSourceName", source_data.get("name"))
                scans.append(scan)

        if not scans:
            payload = self._first_success(
                "GET",
                [
                    {
                        "path": "/scans",
                        "base_url": self.scan_base_url,
                        "scope": "https://purview.azure.net/.default",
                        "params": {"api-version": "2023-09-01-preview"},
                    }
                ],
            )
            scans = self._extract_items(payload)

        return self._as_mapping(scans, ("id", "name"))
    
    def get_classifications(self) -> Dict[str, Any]:
        """Fetch all Classifications/Glossary terms from Purview"""
        logger.info("Fetching Classifications from Purview")
        payload = self._first_success(
            "GET",
            [
                {
                    "path": "/catalog/api/atlas/v2/types/typedefs",
                    "scope": "https://purview.azure.net/.default",
                    "params": {"type": "classification"},
                },
                {
                    "path": "/catalog/api/atlas/v2/types/classificationdef",
                    "scope": "https://purview.azure.net/.default",
                },
            ],
            fixture_name="classifications",
        )

        items = []
        if isinstance(payload, dict) and isinstance(payload.get("classificationDefs"), list):
            items = payload["classificationDefs"]
        else:
            items = self._extract_items(payload)
        return self._as_mapping(items, ("name", "guid", "id"))
    
    def get_lineage(self, asset_id: str) -> Dict[str, Any]:
        """Get lineage for a specific asset"""
        logger.info(f"Fetching lineage for asset: {asset_id}")
        payload = self._first_success(
            "GET",
            [
                {
                    "path": f"/catalog/api/atlas/v2/lineage/{asset_id}",
                    "scope": "https://purview.azure.net/.default",
                },
                {
                    "path": f"/catalog/api/atlas/v2/entity/guid/{asset_id}/lineage",
                    "scope": "https://purview.azure.net/.default",
                },
            ],
        )
        return payload or {}
    
    def get_runtimes(self) -> Dict[str, Any]:
        """Fetch all Integration Runtimes"""
        logger.info("Fetching Integration Runtimes")
        payload = self._first_success(
            "GET",
            [
                {
                    "path": "/integrationruntimes",
                    "base_url": self.scan_base_url,
                    "scope": "https://purview.azure.net/.default",
                    "params": {"api-version": "2023-09-01-preview"},
                },
                {
                    "path": "/scan/integrationruntimes",
                    "base_url": self.scan_base_url,
                    "scope": "https://purview.azure.net/.default",
                    "params": {"api-version": "2023-09-01-preview"},
                },
            ],
            fixture_name="runtimes",
        )
        return self._as_mapping(self._extract_items(payload), ("id", "name"))
    
    def extract_all_metadata(self) -> Dict[str, Any]:
        """
        Extract all metadata from Purview instance
        
        Returns:
            Dictionary containing all extracted metadata
        """
        metadata = {
            "collections": self.get_collections(),
            "data_sources": self.get_data_sources(),
            "assets": self.get_assets(),
            "scans": self.get_scans(),
            "classifications": self.get_classifications(),
            "runtimes": self.get_runtimes(),
        }
        
        logger.info("Metadata extraction complete")
        return metadata


def get_purview_client(account_url: str, credential=None) -> PurviewClient:
    """Factory function to create and configure a Purview client"""
    client = PurviewClient(credential)
    client.set_account(account_url)
    return client
