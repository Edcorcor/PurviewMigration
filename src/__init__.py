"""
Purview Data Governance Audit & Migration System
Python module for Azure Purview, Fabric, and Key Vault operations
"""

__version__ = "1.0.0"
__author__ = "GitHub Copilot"

from .config_manager import ConfigManager, get_config_manager, get_config
from .purview_client import PurviewClient, get_purview_client
from .unified_catalog_client import UnifiedCatalogClient, get_unified_catalog_client
from .key_vault_connector import KeyVaultConnector, get_key_vault_connector

__all__ = [
    "ConfigManager",
    "get_config_manager",
    "get_config",
    "PurviewClient",
    "get_purview_client",
    "UnifiedCatalogClient",
    "get_unified_catalog_client",
    "KeyVaultConnector",
    "get_key_vault_connector",
]
