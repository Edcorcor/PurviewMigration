"""
Configuration Manager
Handles environment-aware configuration loading with support for multiple environments
and secret resolution from Azure Key Vault or environment variables.
"""

import os
import json
import yaml
from typing import Dict, Any, Optional
from pathlib import Path
try:
    from pydantic import BaseSettings, Field
except ImportError:
    from pydantic_settings import BaseSettings
    from pydantic import Field


class PurviewAuditConfig(BaseSettings):
    """Configuration model for Purview Audit system"""
    
    # Azure Auth
    azure_tenant_id: str = Field(default_factory=lambda: os.getenv("AZURE_TENANT_ID", ""))
    azure_subscription_id: str = Field(default_factory=lambda: os.getenv("AZURE_SUBSCRIPTION_ID", ""))
    
    # Purview
    purview_account_names: list = Field(default_factory=list)
    purview_auto_discover: bool = True
    
    # Unified Catalog / Fabric
    unified_catalog_enabled: bool = True
    fabric_workspace_name: str = "PurviewAuditWorkspace"
    fabric_workspace_id: Optional[str] = Field(default_factory=lambda: os.getenv("FABRIC_WORKSPACE_ID"))
    
    # Key Vault
    key_vault_name: str = Field(default_factory=lambda: os.getenv("KEY_VAULT_NAME", ""))
    check_fabric_connection: bool = True
    
    # Spark
    spark_app_name: str = "PurviewAuditSpark"
    spark_memory: str = "4g"
    spark_cores: int = 4
    
    # Output
    output_data_format: str = "parquet"
    output_overwrite: bool = True
    output_destination: str = "fabric"  # fabric, local, adls
    
    # Logging
    logging_level: str = "INFO"
    logging_format: str = "json"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


class ConfigManager:
    """Manages configuration loading and environment variable resolution"""
    
    def __init__(self, config_dir: str = "./config"):
        self.config_dir = Path(config_dir)
        self.config: Optional[Dict[str, Any]] = None
        self.pydantic_config: Optional[PurviewAuditConfig] = None
    
    def load_yaml_config(self) -> Dict[str, Any]:
        """Load configuration from environment.yml"""
        config_file = self.config_dir / "environment.yml"
        
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_file}")
        
        with open(config_file, 'r') as f:
            raw_config = yaml.safe_load(f)
        
        # Resolve environment variables in config (${VAR_NAME} format)
        self.config = self._resolve_env_vars(raw_config)
        return self.config
    
    def load_pydantic_config(self) -> PurviewAuditConfig:
        """Load configuration using Pydantic for validation"""
        self.pydantic_config = PurviewAuditConfig()
        return self.pydantic_config
    
    def _resolve_env_vars(self, obj: Any) -> Any:
        """Recursively resolve ${VAR_NAME} references in config"""
        if isinstance(obj, dict):
            return {k: self._resolve_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._resolve_env_vars(item) for item in obj]
        elif isinstance(obj, str):
            if obj.startswith("${") and obj.endswith("}"):
                var_name = obj[2:-1]
                default = ""
                if ":" in var_name:
                    var_name, default = var_name.split(":", 1)
                return os.getenv(var_name, default)
            return obj
        return obj
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get config value by dot-notation key (e.g., 'azure.tenant_id')"""
        if self.config is None:
            self.load_yaml_config()
        
        keys = key.split(".")
        value = self.config
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def validate(self) -> tuple[bool, list[str]]:
        """Validate required configuration is present"""
        errors = []
        
        if not self.get("azure.tenant_id"):
            errors.append("AZURE_TENANT_ID not set")
        if not self.get("azure.subscription_id"):
            errors.append("AZURE_SUBSCRIPTION_ID not set")
        if not self.get("key_vault.vault_name"):
            errors.append("KEY_VAULT_NAME not set")
        
        return len(errors) == 0, errors


# Global instance
_config_manager = None


def get_config_manager() -> ConfigManager:
    """Get or create global config manager instance"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
        _config_manager.load_yaml_config()
    return _config_manager


def get_config(key: str, default: Any = None) -> Any:
    """Convenience function to get config value"""
    return get_config_manager().get(key, default)
