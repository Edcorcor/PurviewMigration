#!/usr/bin/env python3
"""Quick test of all modules"""

import sys
sys.path.insert(0, 'src')

print("="*60)
print("SYSTEM TEST - Module Import & Configuration")
print("="*60)

# Test 1: Imports
print("\n1. Testing module imports...")
try:
    from config_manager import get_config_manager
    print("   ✓ Config manager")
except Exception as e:
    print(f"   ✗ Config manager: {e}")
    sys.exit(1)

try:
    from purview_client import PurviewClient
    print("   ✓ Purview client")
except Exception as e:
    print(f"   ✗ Purview client: {e}")
    sys.exit(1)

try:
    from unified_catalog_client import UnifiedCatalogClient
    print("   ✓ Unified Catalog client")
except Exception as e:
    print(f"   ✗ Unified Catalog client: {e}")
    sys.exit(1)

try:
    from key_vault_connector import KeyVaultConnector
    print("   ✓ Key Vault connector")
except Exception as e:
    print(f"   ✗ Key Vault connector: {e}")
    sys.exit(1)

# Test 2: Configuration loading
print("\n2. Testing configuration loading...")
try:
    cfg = get_config_manager()
    print("   ✓ Config file loaded from config/environment.yml")
except Exception as e:
    print(f"   ✗ Config loading failed: {e}")
    sys.exit(1)

# Test 3: Configuration values
print("\n3. Configuration values:")
try:
    values = {
        "Purview Auto-discover": cfg.get("purview.auto_discover"),
        "Fabric Workspace": cfg.get("fabric.workspace_name"),
        "Output Format": cfg.get("output.data_format"),
        "Output Destination": cfg.get("output.destination"),
        "Logging Level": cfg.get("logging.level"),
    }
    
    for key, value in values.items():
        print(f"   • {key}: {value}")
except Exception as e:
    print(f"   ✗ Configuration read failed: {e}")
    sys.exit(1)

print("\n" + "="*60)
print("✅ ALL TESTS PASSED - System ready for notebook execution")
print("="*60)
print("\nNext steps:")
print("1. Set environment variables: AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID, KEY_VAULT_NAME")
print("2. Run: jupyter notebook notebooks/")
print("3. Execute: 00-Setup.ipynb")
