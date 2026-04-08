# Purview Data Governance Audit & Migration Toolkit

A comprehensive Spark-based system to extract, audit, and report on all Purview Data Governance entities and prepare for migration to a new Data Governance Landing Zone.

## Overview

**Phase 1: Audit & Report** (Current)
- Extract all entities from Purview (Collections, Data Sources, Assets, Scans, Runtimes, Key Vaults)
- Extract all Data Products and assets from Unified Catalog with Data Quality scores
- Validate Key Vault connectivity to Fabric
- Store deduplicated data in Fabric Workspace
- Generate comprehensive Power BI report showing relationships and coverage

**Phase 2: Migration** (Future)
- Migrate validated entities to new Purview instance in Data Governance Landing Zone
- Preserve all relationships and metadata
- Handle multi-instance scenarios with domain mapping

## Architecture

```
┌─ Jupyter Notebooks (Orchestration)
│   ├─ 00-Setup (Environment validation, multi-instance discovery)
│   ├─ 01-Purview-Extract (Full data export + raw persistence)
│   ├─ 02-UnifiedCatalog-Extract (Data Products & Quality + raw persistence)
│   ├─ 03-Transform-Data (Spark jobs for deduplication, dimensions, and relationships)
│   ├─ 04-KeyVault-Validation (Connectivity validation and remediation reporting)
│   └─ 05-Load-Fabric (Publish to Fabric path or local staging)
│
├─ Python Modules (/src)
│   ├─ purview_client.py (SDK wrapper)
│   ├─ unified_catalog_client.py (Fabric SDK)
│   ├─ key_vault_connector.py (Key Vault & Fabric validation)
│   └─ config_manager.py (Environment-aware configuration)
│
├─ Power BI Assets (/powerbi)
│   ├─ semantic_model.json (starter semantic model)
│   ├─ measures.dax (starter measures)
│   └─ report_spec.md (report layout and visuals)
│
├─ Configuration (/config)
│   └─ environment.yml (Multi-environment settings, uses env vars)
│
└─ Data (/data)
    ├─ raw/ (Downloaded from Purview/Catalog)
    ├─ processed/ (Transformed)
    └─ reports/ (PBI-ready datasets)
```

## Quick Start

### Prerequisites
- Python 3.10+
- Jupyter
- Azure CLI (logged in)
- Spark (PySpark)
- Access to: Azure Purview, Microsoft Fabric, Azure Key Vault

### Setup

1. **Clone and install:**
   ```bash
   cd PurviewMigration
   pip install -r requirements.txt
   jupyter notebook
   ```

2. **Configure environment:**
   - Set environment variables or use Azure Key Vault:
     ```bash
     export AZURE_TENANT_ID="..."
     export AZURE_SUBSCRIPTION_ID="..."
     export KEY_VAULT_NAME="..."
     ```

3. **Run notebooks in order:**
   - `00-Setup.ipynb` - Validates environment and discovers Purview instances
   - `01-Purview-Extract.ipynb` - Exports all Purview entities
   - `02-UnifiedCatalog-Extract.ipynb` - Exports Data Products and quality metrics
   - `03-Transform-Data.ipynb` - Deduplicates and builds relationships
   - `04-KeyVault-Check.ipynb` - Validates Key Vault ↔ Fabric connectivity
   - `05-Load-Fabric.ipynb` - Writes final datasets to Fabric Workspace

## Features

✅ **Multi-Instance Support**
- Auto-discovers all Purview instances in subscription
- Prompts user to designate primary instance
- Extracts from all, tags with instance origin

✅ **Comprehensive Extraction**
- All data map entities (Collections, Data Sources, Scans, etc.)
- All Unified Catalog entities (Data Products, Data Quality scores)
- Relationship mapping and lineage

✅ **Data Quality**
- Deduplication across instances
- Validation of required fields
- Orphan entity detection

✅ **Fabric Integration**
- Auto-creates Fabric workspace if needed
- Writes to configured OneLake path when available, otherwise stages locally
- Ready for Power BI semantic models

✅ **Key Vault Health Check**
- Validates existing Key Vault connections
- Identifies disconnected vaults
- Provides Fabric wiring checklist

✅ **Environment Flexibility**
- Runs on local Spark, Synapse, or Fabric
- Cloud-agnostic configuration (uses env vars)
- No hardcoded credentials

## Output

### Data Assets (in Fabric Workspace)
- **collections.parquet** - All Collections with hierarchy
- **data_sources.parquet** - All Data Sources with scans
- **assets.parquet** - All cataloged assets with lineage
- **scans.parquet** - Scan configurations and runs
- **runtimes.parquet** - Integration runtimes
- **key_vaults.parquet** - Key Vaults with connection status
- **data_products.parquet** - Data Products from Unified Catalog
- **data_quality.parquet** - Data Quality scores and metrics
- **relationships.parquet** - Entity relationships graph

### Reports
- **audit_summary.json** - Counts, coverage, gaps
- **key_vault_connectivity.json** - Connectivity status per vault
- **multi_instance_map.json** - Instance topology

## Power BI Integration

1. Connect Power BI to Fabric Workspace
2. Build models from parquet files
3. Suggested visuals:
   - **Collection Hierarchy** - Tree map of collections & assets
   - **Data Source Coverage** - Scan success rates
   - **Data Quality Dashboard** - Quality scores by Data Product
   - **Key Vault Status** - Fabric connectivity heat map
   - **Asset Lineage** - Network diagram of relationships

Starter report assets are included in [powerbi/semantic_model.json](powerbi/semantic_model.json), [powerbi/measures.dax](powerbi/measures.dax), and [powerbi/report_spec.md](powerbi/report_spec.md).

## Current Validation Status

- Repository backlog items are implemented in code.
- Live Fabric provisioning still depends on tenant permissions and working credentials at runtime.
- Use `python validate.py` and the provisioning portal to verify access in your environment.

## Naming Convention (Disney Villain Theme 🦹)

Future team members will be named after Disney villains:
- Data Engineers → Maleficent, Cruella, Ursula, Scar, Gaston...
- Data Analysts → Jafar, Captain Hook, Mother Gothel...
- Platform → The Evil Queen, Hades, Shan Yu...

## Next Steps (Phase 2)

Once audit is complete and approved:
1. Create new Purview instance in Data Governance Landing Zone
2. Migrate entities using validated relationships
3. Decommission old instance
4. Update all lineage pointers

## Troubleshooting

### "No Purview instances found"
- Check Azure CLI login: `az account show`
- Verify subscription ID in environment
- Ensure account has "Purview Administrator" or similar role

### "Key Vault not found in Fabric"
- Run `04-KeyVault-Check.ipynb` for remediation steps
- May need to wire Key Vault to Fabric explicitly

### "Unified Catalog returns empty"
- Verify Fabric workspace has Premium capacity
- Check that Data Products exist in target Fabric

## Support

For issues, check:
- Notebook cell error messages (detailed Azure SDK errors)
- Logs in `/data/logs/`
- Azure Activity Log in portal
