#!/usr/bin/env python3
"""
Validation script to test Purview Data Governance audit system connectivity
Run this before executing notebooks to catch issues early
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from azure.identity import DefaultAzureCredential
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_env_vars():
    """Check required environment variables"""
    print("\n✓ Checking environment variables...")
    
    required = [
        "AZURE_TENANT_ID",
        "AZURE_SUBSCRIPTION_ID",
        "KEY_VAULT_NAME"
    ]
    
    missing = []
    for var in required:
        value = os.getenv(var)
        if value:
            print(f"  ✓ {var}: {'*' * 8}")
        else:
            print(f"  ✗ {var}: NOT SET")
            missing.append(var)
    
    return len(missing) == 0, missing


def check_azure_auth():
    """Test Azure authentication"""
    print("\n✓ Checking Azure authentication...")
    
    try:
        credential = DefaultAzureCredential()
        token = credential.get_token("https://management.azure.com/.default")
        print(f"  ✓ Authentication successful")
        print(f"  ✓ Token expires: {token.expires_on}")
        return True
    except Exception as e:
        print(f"  ✗ Authentication failed: {e}")
        return False


def check_purview_discovery():
    """Test Purview instance discovery"""
    print("\n✓ Checking Purview instance discovery...")
    
    try:
        from purview_client import PurviewClient
        credential = DefaultAzureCredential()
        subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID")
        
        if not subscription_id:
            print("  ⚠ AZURE_SUBSCRIPTION_ID not set - skipping")
            return True
        
        instances = PurviewClient.discover_purview_instances(subscription_id, credential)
        
        if instances:
            print(f"  ✓ Found {len(instances)} Purview instance(s)")
            for inst in instances:
                print(f"    - {inst['name']} ({inst['location']})")
            return True
        else:
            print("  ⚠ No Purview instances found")
            return True  # Not a hard failure
    
    except Exception as e:
        print(f"  ✗ Purview discovery failed: {e}")
        return False


def check_key_vault():
    """Test Key Vault access"""
    print("\n✓ Checking Key Vault connectivity...")
    
    try:
        from key_vault_connector import KeyVaultConnector
        credential = DefaultAzureCredential()
        vault_name = os.getenv("KEY_VAULT_NAME")
        
        if not vault_name:
            print("  ⚠ KEY_VAULT_NAME not set - skipping")
            return True
        
        connector = KeyVaultConnector(vault_name, credential)
        accessible = connector.check_key_vault_access()
        
        if accessible:
            secrets = connector.get_vault_secrets_info()
            print(f"  ✓ Key Vault accessible - {len(secrets)} secret(s)")
            return True
        else:
            print(f"  ✗ Key Vault not accessible")
            return False
    
    except Exception as e:
        print(f"  ✗ Key Vault check failed: {e}")
        return False


def check_config_file():
    """Test configuration file loading"""
    print("\n✓ Checking configuration file...")
    
    try:
        from config_manager import get_config_manager
        config_mgr = get_config_manager()
        valid, errors = config_mgr.validate()
        
        if valid:
            print("  ✓ Configuration file valid")
            return True
        else:
            print("  ⚠ Configuration warnings:")
            for error in errors:
                print(f"    - {error}")
            return True  # Warnings only
    
    except Exception as e:
        print(f"  ✗ Configuration check failed: {e}")
        return False


def main():
    print("=" * 60)
    print("Purview Data Governance Audit - Pre-flight Check")
    print("=" * 60)
    
    checks = [
        ("Environment Variables", check_env_vars),
        ("Azure Authentication", check_azure_auth),
        ("Purview Discovery", check_purview_discovery),
        ("Key Vault Access", check_key_vault),
        ("Configuration File", check_config_file),
    ]
    
    results = []
    for name, check_func in checks:
        try:
            if name == "Environment Variables":
                result, missing = check_func()
            else:
                result = check_func()
            results.append((name, result))
        except Exception as e:
            logger.error(f"Error in {name}: {e}")
            results.append((name, False))
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} checks passed")
    
    if passed == total:
        print("\n✓ All checks passed! Ready to run notebooks.")
        print("\nNext step: jupyter notebook")
        return 0
    else:
        print("\n⚠ Some checks failed. Review above and retry.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
