#!/usr/bin/env python3
"""Quick test of all modules"""

import sys
from pathlib import Path
sys.path.insert(0, 'src')

ROOT = Path(__file__).parent

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

# Test 4: Downstream notebook presence
print("\n4. Notebook deliverables:")
try:
    notebook_paths = [
        ROOT / "notebooks" / "03-Transform-Data.ipynb",
        ROOT / "notebooks" / "04-KeyVault-Validation.ipynb",
        ROOT / "notebooks" / "05-Load-Fabric.ipynb",
    ]
    for notebook_path in notebook_paths:
        if notebook_path.exists() and notebook_path.stat().st_size > 0:
            print(f"   ✓ {notebook_path.name}")
        else:
            raise FileNotFoundError(f"Notebook missing or empty: {notebook_path}")
except Exception as e:
    print(f"   ✗ Notebook validation failed: {e}")
    sys.exit(1)

# Test 5: Power BI starter assets
print("\n5. Power BI starter assets:")
try:
    powerbi_paths = [
        ROOT / "powerbi" / "semantic_model.json",
        ROOT / "powerbi" / "report_spec.md",
        ROOT / "powerbi" / "measures.dax",
    ]
    for asset_path in powerbi_paths:
        if asset_path.exists() and asset_path.stat().st_size > 0:
            print(f"   ✓ {asset_path.name}")
        else:
            raise FileNotFoundError(f"Power BI asset missing or empty: {asset_path}")
except Exception as e:
    print(f"   ✗ Power BI asset validation failed: {e}")
    sys.exit(1)

print("\n" + "="*60)
print("✅ ALL TESTS PASSED - System ready for notebook execution")
print("="*60)
print("\nNext steps:")
print("1. Set environment variables: AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID, KEY_VAULT_NAME")
print("2. Run: jupyter notebook notebooks/")
print("3. Execute: 00-Setup.ipynb")
