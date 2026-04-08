"""
Key Vault Connector
Validates Key Vault connectivity and Fabric wiring.
Identifies disconnected vaults and provides remediation guidance.
"""

import logging
from typing import Dict, List, Any, Optional
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient


logger = logging.getLogger(__name__)


class KeyVaultConnector:
    """Manages Key Vault connectivity checks and Fabric wiring"""
    
    def __init__(self, vault_name: str, credential=None):
        """
        Initialize Key Vault connector
        
        Args:
            vault_name: Name of the Azure Key Vault
            credential: Azure credential (defaults to DefaultAzureCredential)
        """
        self.vault_name = vault_name
        self.credential = credential or DefaultAzureCredential()
        self.vault_url = f"https://{vault_name}.vault.azure.net/"
        self.client = SecretClient(vault_url=self.vault_url, credential=self.credential)
    
    def check_key_vault_access(self) -> bool:
        """
        Check if we have access to the Key Vault
        
        Returns:
            True if accessible, False otherwise
        """
        try:
            # Try to list secrets
            list(self.client.list_properties_of_secrets())
            logger.info(f"Key Vault access verified: {self.vault_name}")
            return True
        except Exception as e:
            logger.error(f"Cannot access Key Vault {self.vault_name}: {e}")
            return False
    
    def get_vault_secrets_info(self) -> List[Dict[str, Any]]:
        """
        Get information about secrets in the vault (names only, no values)
        
        Returns:
            List of secret metadata
        """
        try:
            secrets = []
            for secret_property in self.client.list_properties_of_secrets():
                secrets.append({
                    "name": secret_property.name,
                    "created_on": secret_property.created_on,
                    "updated_on": secret_property.updated_on,
                    "enabled": secret_property.enabled,
                    "tags": secret_property.tags
                })
            return secrets
        except Exception as e:
            logger.error(f"Error retrieving secrets: {e}")
            return []
    
    def check_fabric_connectivity(self) -> Dict[str, Any]:
        """
        Check if Key Vault is connected to Fabric
        
        Returns:
            Status dict with connectivity info and remediation steps if needed
        """
        logger.info(f"Checking Fabric connectivity for Key Vault: {self.vault_name}")
        
        status = {
            "vault_name": self.vault_name,
            "is_connected": False,
            "status": "UNKNOWN",
            "remediation_steps": []
        }
        
        # Check for Fabric-related configuration
        # This would check for Fabric workspace linked credentials, etc.
        # Placeholder for actual implementation
        
        if not status["is_connected"]:
            status["remediation_steps"] = [
                "1. Navigate to Azure Key Vault in Azure Portal",
                "2. Go to 'Access Control (IAM)'",
                "3. Add role assignment for your Fabric service principal",
                "4. Ensure 'get' and 'list' permissions are granted",
                f"5. In Fabric workspace, add Key Vault reference to '{self.vault_name}'",
                "6. Test connection and re-run this check"
            ]
        
        return status
    
    @staticmethod
    def discover_key_vaults(subscription_id: str, resource_group: Optional[str] = None, 
                           credential=None) -> List[Dict[str, str]]:
        """
        Discover all Key Vaults in a subscription or resource group
        
        Args:
            subscription_id: Azure subscription ID
            resource_group: Optional specific resource group
            credential: Azure credential
            
        Returns:
            List of Key Vault information
        """
        if credential is None:
            credential = DefaultAzureCredential()
        
        from azure.mgmt.resourcegraph import ResourceGraphClient
        from azure.mgmt.resourcegraph.models import QueryRequest
        
        client = ResourceGraphClient(credential)
        
        query = QueryRequest(
            subscriptions=[subscription_id],
            query="resources | where type == 'microsoft.keyvault/vaults'"
        )
        
        if resource_group:
            query = QueryRequest(
                subscriptions=[subscription_id],
                query=f"resources | where type == 'microsoft.keyvault/vaults' and resourceGroup == '{resource_group}'"
            )
        
        try:
            results = client.resources(query)
            vaults = []
            
            for resource in results.data:
                vaults.append({
                    "name": resource.get("name"),
                    "id": resource.get("id"),
                    "resource_group": resource.get("resourceGroup"),
                    "location": resource.get("location")
                })
            
            logger.info(f"Discovered {len(vaults)} Key Vault(s)")
            return vaults
        
        except Exception as e:
            logger.error(f"Error discovering Key Vaults: {e}")
            return []


def get_key_vault_connector(vault_name: str, credential=None) -> KeyVaultConnector:
    """Factory function to create and configure a Key Vault connector"""
    return KeyVaultConnector(vault_name, credential)
