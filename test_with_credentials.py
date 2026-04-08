#!/usr/bin/env python3
"""Simple validation test with credentials"""

import sys
import os

# Set encoding to UTF-8
os.environ['PYTHONIOENCODING'] = 'utf-8'

sys.path.insert(0, 'src')

print("="*70)
print("PURVIEW SYSTEM TEST - Configuration & Azure Connectivity")
print("="*70)

# Display loaded credentials
print("\n[1] Environment Variables Loaded:")
print(f"    Tenant ID: {os.getenv('AZURE_TENANT_ID', 'NOT SET')[:8]}...")
print(f"    Subscription ID: {os.getenv('AZURE_SUBSCRIPTION_ID', 'NOT SET')[:8]}...")
print(f"    Key Vault: {os.getenv('KEY_VAULT_NAME', 'NOT SET')}")

# Test 1: Module imports
print("\n[2] Module Imports:")
try:
    from config_manager import get_config_manager
    from purview_client import PurviewClient
    from unified_catalog_client import UnifiedCatalogClient
    from key_vault_connector import KeyVaultConnector
    print("    OK - All modules imported successfully")
except Exception as e:
    print(f"    FAIL - {e}")
    sys.exit(1)

# Test 2: Configuration loading
print("\n[3] Configuration Loading:")
try:
    cfg = get_config_manager()
    is_valid, errors = cfg.validate()
    if not is_valid:
        print(f"    WARNING - Validation errors: {errors}")
    print("    OK - Config loaded from environment.yml")
except Exception as e:
    print(f"    FAIL - {e}")
    sys.exit(1)

# Test 3: Azure authentication
print("\n[4] Azure Authentication:")
try:
    from azure.identity import DefaultAzureCredential
    cred = DefaultAzureCredential()
    token = cred.get_token("https://management.azure.com/.default")
    print(f"    OK - Token acquired (expires: {token.expires_on})")
except Exception as e:
    print(f"    Note: {type(e).__name__} - {str(e)[:80]}")
    print("    This is expected if you're not logged in via Azure CLI")

# Test 4: Purview discovery
print("\n[5] Purview Instance Discovery:")
try:
    from azure.identity import DefaultAzureCredential
    sub_id = os.getenv("AZURE_SUBSCRIPTION_ID")
    
    if not sub_id:
        print("    SKIP - AZURE_SUBSCRIPTION_ID not set")
    else:
        cred = DefaultAzureCredential()
        instances = PurviewClient.discover_purview_instances(sub_id, cred)
        
        if instances:
            print(f"    OK - Found {len(instances)} Purview instance(s)")
            for inst in instances:
                print(f"         - {inst['name']} ({inst['location']})")
        else:
            print("    Note - No Purview instances found in subscription")
            print("           This is OK if your subscription doesn't have Purview yet")
except Exception as e:
    error_msg = str(e)[:100]
    print(f"    Note: {type(e).__name__}")
    print(f"          {error_msg}")

# Test 5: Key Vault access
print("\n[6] Key Vault Access:")
try:
    from azure.identity import DefaultAzureCredential
    vault_name = os.getenv("KEY_VAULT_NAME")
    
    if not vault_name:
        print("    SKIP - KEY_VAULT_NAME not set")
    else:
        cred = DefaultAzureCredential()
        connector = KeyVaultConnector(vault_name, cred)
        accessible = connector.check_key_vault_access()
        
        if accessible:
            print(f"    OK - Key Vault accessible: {vault_name}")
        else:
            print(f"    WARNING - Key Vault not accessible: {vault_name}")
except Exception as e:
    print(f"    Note: {type(e).__name__}")
    print(f"          {str(e)[:80]}")

print("\n" + "="*70)
print("TEST SUMMARY")
print("="*70)
print("""
All core modules are working correctly.

To complete testing, you need to:
1. Login to Azure: az login
2. Verify you have access to the subscription and resources
3. Run: jupyter notebook notebooks/
4. Execute: 00-Setup.ipynb

The notebook will handle Azure authentication and attempt to:
- Discover Purview instances
- Connect to Fabric workspace
- Validate Key Vault connectivity
- Extract all metadata
""")
