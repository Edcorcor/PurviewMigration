"""Best-effort client for Microsoft Fabric Unified Catalog metadata."""

import json
import logging
import os
from typing import Dict, List, Any, Optional, Iterable

import requests
from azure.identity import DefaultAzureCredential


logger = logging.getLogger(__name__)

BASE_URL = "https://api.fabric.microsoft.com/v1"


class UnifiedCatalogClient:
    """Client for Microsoft Fabric Unified Catalog"""
    
    def __init__(self, workspace_id: str, credential=None):
        """
        Initialize Unified Catalog client
        
        Args:
            workspace_id: Fabric workspace ID
            credential: Azure credential (defaults to DefaultAzureCredential)
        """
        self.workspace_id = workspace_id
        self.credential = credential or DefaultAzureCredential()
        self.session = requests.Session()

    def _headers(self) -> Dict[str, str]:
        token = self.credential.get_token("https://api.fabric.microsoft.com/.default").token
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _load_fixture(self, fixture_name: str) -> Optional[Any]:
        path = os.getenv(f"UNIFIED_CATALOG_{fixture_name.upper()}_FILE")
        if not path:
            return None
        try:
            with open(path, "r", encoding="utf-8") as handle:
                logger.info("Loading Unified Catalog fixture from %s", path)
                return json.load(handle)
        except Exception as exc:
            logger.warning("Could not load Unified Catalog fixture %s: %s", path, exc)
            return None

    @staticmethod
    def _extract_list(payload: Any, keys: Iterable[str] = ("value", "items", "data", "assets")) -> List[Dict[str, Any]]:
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

    def _request_json(self, path: str) -> Optional[Any]:
        if not self.workspace_id:
            return None

        url = path if path.startswith("http") else f"{BASE_URL}{path}"
        response = self.session.get(url, headers=self._headers(), timeout=30)
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise RuntimeError(f"Fabric request failed: {response.status_code} {response.text}")
        if not response.text.strip():
            return {}
        return response.json()

    def _first_success(self, candidates: List[str], fixture_name: Optional[str] = None) -> Optional[Any]:
        fixture = self._load_fixture(fixture_name) if fixture_name else None
        if fixture is not None:
            return fixture

        last_error: Optional[Exception] = None
        for candidate in candidates:
            try:
                result = self._request_json(candidate)
                if result is not None:
                    return result
            except Exception as exc:
                last_error = exc
                logger.debug("Fabric endpoint attempt failed for %s: %s", candidate, exc)

        if last_error is not None:
            logger.warning("No Fabric endpoint succeeded for %s: %s", fixture_name or "request", last_error)
        return None

    def _workspace_items(self) -> List[Dict[str, Any]]:
        payload = self._first_success([f"/workspaces/{self.workspace_id}/items"], fixture_name="items")
        return self._extract_list(payload)
    
    def get_data_products(self) -> List[Dict[str, Any]]:
        """
        Fetch all Data Products from Unified Catalog
        
        Returns:
            List of Data Product records with metadata
        """
        logger.info(f"Fetching Data Products from workspace: {self.workspace_id}")

        payload = self._first_success(
            [
                f"/workspaces/{self.workspace_id}/dataProducts",
                f"/workspaces/{self.workspace_id}/items?type=DataProduct",
            ],
            fixture_name="data_products",
        )
        items = self._extract_list(payload)
        if items:
            return items

        return [
            item for item in self._workspace_items()
            if str(item.get("type", "")).lower() in {"dataproduct", "data product"}
        ]
    
    def get_data_product_assets(self, data_product_id: str) -> List[Dict[str, Any]]:
        """
        Get all assets in a specific Data Product
        
        Args:
            data_product_id: ID of the Data Product
            
        Returns:
            List of assets in the Data Product
        """
        logger.info(f"Fetching assets for Data Product: {data_product_id}")
        payload = self._first_success(
            [
                f"/workspaces/{self.workspace_id}/dataProducts/{data_product_id}/assets",
                f"/workspaces/{self.workspace_id}/items/{data_product_id}/relatedItems",
            ]
        )
        items = self._extract_list(payload)
        if items:
            return items

        detail = self._first_success([f"/workspaces/{self.workspace_id}/items/{data_product_id}"])
        if isinstance(detail, dict):
            for key in ("assets", "items", "children"):
                value = detail.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        return []
    
    def get_data_quality_scores(self) -> List[Dict[str, Any]]:
        """
        Fetch all Data Quality scores from Unified Catalog
        
        Returns:
            List of data quality records with scores and metrics
        """
        logger.info("Fetching Data Quality scores from Unified Catalog")

        payload = self._first_success(
            [
                f"/workspaces/{self.workspace_id}/dataQuality/metrics",
                f"/workspaces/{self.workspace_id}/qualityScores",
            ],
            fixture_name="quality_scores",
        )
        items = self._extract_list(payload)
        if items:
            return items

        derived_scores: List[Dict[str, Any]] = []
        for asset in self._workspace_items():
            quality = asset.get("quality") or asset.get("dataQuality") or {}
            if isinstance(quality, dict) and quality:
                derived_scores.append(
                    {
                        "assetId": asset.get("id"),
                        "assetName": asset.get("displayName") or asset.get("name"),
                        "score": quality.get("score", 0),
                        "status": quality.get("status"),
                        "dimensions": quality.get("dimensions", {}),
                        "dataProductId": asset.get("dataProductId"),
                    }
                )
        return derived_scores
    
    def get_domains(self) -> List[Dict[str, Any]]:
        """Fetch all Domains from Unified Catalog"""
        logger.info("Fetching Domains from Unified Catalog")
        payload = self._first_success(
            [
                f"/workspaces/{self.workspace_id}/domains",
                f"/workspaces/{self.workspace_id}/items?type=Domain",
            ],
            fixture_name="domains",
        )
        items = self._extract_list(payload)
        if items:
            return items

        return [
            item for item in self._workspace_items()
            if str(item.get("type", "")).lower() == "domain"
        ]
    
    def get_domain_content(self, domain_id: str) -> Dict[str, Any]:
        """Get all content (Data Products, assets) in a domain"""
        logger.info(f"Fetching content for domain: {domain_id}")
        payload = self._first_success(
            [
                f"/workspaces/{self.workspace_id}/domains/{domain_id}",
                f"/workspaces/{self.workspace_id}/items/{domain_id}",
            ]
        )
        return payload or {}
    
    def extract_all_catalog_metadata(self) -> Dict[str, Any]:
        """
        Extract all metadata from Unified Catalog
        
        Returns:
            Dictionary containing all Unified Catalog metadata
        """
        metadata = {
            "domains": self.get_domains(),
            "data_products": self.get_data_products(),
            "data_quality": self.get_data_quality_scores(),
        }
        
        logger.info("Unified Catalog metadata extraction complete")
        return metadata


def get_unified_catalog_client(workspace_id: str, credential=None) -> UnifiedCatalogClient:
    """Factory function to create and configure a Unified Catalog client"""
    return UnifiedCatalogClient(workspace_id, credential)
