# Quick Start Guide

## 5-Minute Setup

### 1️⃣ Prerequisites
```bash
# Python 3.10+
python --version

# Azure CLI - already logged in
az account show

# Required environment variables
export AZURE_TENANT_ID="your-tenant-id"
export AZURE_SUBSCRIPTION_ID="your-subscription-id"
export KEY_VAULT_NAME="your-keyvault-name"

# Optional
export FABRIC_WORKSPACE_ID="your-workspace-id"
```

### 2️⃣ Install Dependencies
```bash
pip install -r requirements.txt
```

### 3️⃣ Start Jupyter
```bash
cd notebooks
jupyter notebook
```

## Execution Flow

### Phase 1: Audit & Report (Current)

Run notebooks in this order:

#### 1. **00-Setup.ipynb**
- Validates Azure authentication
- Discovers Purview instances in your subscription
- Prompts: *"Which Purview is PRIMARY?"* (if multiple found)
- Validates Key Vault access
- Checks Fabric workspace readiness

**Expected output**:
```
✓ Discovered 2 Purview instance(s)
  [1] purview-prod (PRIMARY)
  [2] purview-dr (non-primary, tag for future domain)
✓ Key Vault: mytestkeyvault (connected to Fabric)
✓ Fabric workspace: PurviewAuditWorkspace (ready)
```

#### 2. **01-Purview-Extract.ipynb**
Extracts ALL metadata from Purview:
- Collections (hierarchical)
- Data Sources (snowflake, sql, dbfs, adls2, etc.)
- Assets (tables, columns, processes)
- Scans & scan runs
- Classifications & business metadata
- Integration runtimes

**Expected output**: 
```
✓ Total collections extracted: 45
✓ Total data sources extracted: 12
✓ Total assets extracted: 3,247
✓ Total scans extracted: 89
✓ Total classifications extracted: 23
✓ Total runtimes extracted: 4
```

#### 3. **02-UnifiedCatalog-Extract.ipynb**
Extracts Fabric Unified Catalog:
- Data Products
- Assets within each Data Product
- Data Quality scores (with dimension details)
- Domains
- Ownership & certification status

**Expected output**:
```
✓ Data Products extracted: 8
✓ Catalog assets extracted: 1,204
✓ Data Quality scores: 892 (avg: 85.3%)
✓ Domains extracted: 3
```

#### 4. **03-Transform-Data.ipynb** *(Next)*
Normalizes both datasets:
- Deduplicate Purview assets found in multiple accounts
- Map Purview assets ↔ Fabric Data Products using name/ID matching
- Create relationship graph (parent-child, lineage, ownership)
- Build Power BI-ready star schema
- Completeness checks & gap report

**Output**: Spark DataFrames ready for Fabric

#### 5. **04-KeyVault-Validation.ipynb** *(Next)*
Validates connectivity:
- Lists all Key Vaults in subscription
- Checks each vault's Fabric connectivity status
- Generates remediation checklist for disconnected vaults
- Reports ready-to-use vs needs-wiring

#### 6. **05-Load-Fabric.ipynb** *(Final)*
Persists all data:
- Writes to Fabric Workspace Lakehouse (Delta format)
- Creates tables: collections, sources, assets, quality, products, relationships
- Registers for Power BI consumption
- Snapshot timestamp & immutability for audit trail

---

## Configuration Files

### `config/environment.yml`
```yaml
azure:
  tenant_id: "${AZURE_TENANT_ID}"         # env vars supported
  subscription_id: "${AZURE_SUBSCRIPTION_ID}"

purview:
  account_names: []                        # leave empty for auto-discover
  auto_discover: true

fabric:
  workspace_name: "PurviewAuditWorkspace"
  workspace_id: "${FABRIC_WORKSPACE_ID}"   # auto-create if not provided

key_vault:
  vault_name: "${KEY_VAULT_NAME}"
  check_fabric_connection: true

output:
  destination: "fabric"                    # or "local" for testing
  data_format: "parquet"
```

---

## Notebook Parameters (Optional)

If running in **Databricks** or **Azure Synapse**:

```python
# These are auto-set by 00-Setup; you can override via widgets:
dbutils.widgets.text("subscription_id", os.getenv("AZURE_SUBSCRIPTION_ID"))
dbutils.widgets.text("primary_account", "")       # Leave empty if unsure
dbutils.widgets.text("fabric_workspace_id", "")   # Will auto-create if empty
```

---

## Troubleshooting

### "No Purview instances found"
```bash
# Check you're logged in to correct subscription
az account show

# Check permissions - need "Purview Administrator" or similar
az role assignment list --assignee <your-email> --subscription <sub-id>
```

### "Cannot access Key Vault"
```bash
# Verify you have Get + List permissions
az keyvault permission list --name <vault-name> --object-id <your-object-id>

# Grant permissions if needed
az keyvault set-policy --name <vault-name> \
  --object-id <your-object-id> \
  --secret-permissions get list
```

### "Fabric workspace not found"
In the notebook, leave `fabric_workspace_id` empty - it will create one automatically using `FABRIC_WORKSPACE_NAME` config.

### Distributed/Multi-account scenarios
- If **multiple Purview accounts** exist, the setup notebook will ask which is primary
- All instances are extracted; non-primary ones are tagged for future domain mapping
- Future Purview rebuild can create separate Domains per account

---

## Power BI Integration

After **05-Load-Fabric.ipynb** completes:

1. Open **Power BI Desktop**
2. **Get Data** → **Fabric** 
3. Select workspace: **PurviewAuditWorkspace**
4. Import tables:
   - `collections_silver` (dimensions)
   - `data_sources_silver` (dimensions)
   - `assets_silver` (dimensions)
   - `data_products_silver` (dimensions)
   - `data_quality_scores_silver` (facts)
   - `scan_runs_silver` (facts)
   - `relationships_silver` (graph edges)

5. Build model with relationships
6. Create visuals:
   - **Hierarchy**: Collections → Data Sources → Scans → Assets
   - **Coverage**: % of assets with classifications/lineage/quality scores
   - **Quality Dashboard**: Avg score by Data Product, trend over time
   - **Key Vault Status**: Connected vs needs-wiring heatmap
   - **Lineage Network**: Graph of upstream/downstream relationships

---

## Phase 2: Migration (Future)

Once audit is **COMPLETE & APPROVED**:

1. Create new Purview instance in **Data Governance Landing Zone**
2. Run future `06-Migrate.ipynb` notebook:
   - Provisions new instance
   - Recreates collections, classifications, domains
   - Re-registers data sources with new runtime endpoints
   - Sets up quality rules
   - Validates artifact parity
3. Decommission old instance
4. Update all lineage pointers

---

## Support & Logging

### View Logs
```bash
# Logs are written to notebooks (inline)
# For file logs, check: /data/logs/audit_TIMESTAMP.log
```

### Common Log Patterns
- ✓ Green checkmark = Success
- ⚠ Yellow warning = Skipped/warnings
- ✗ Red error = Blocked - requires action

### Get Help
- Check notebook cell output for Azure SDK error details
- Review Azure Activity Log in Portal
- Verify Azure RBAC role assignments

---

## Naming Convention 🦹‍♀️

Future hires will be named after **Disney Villains**:

- **Data Engineers**: Maleficent, Ursula, Cruella, Scar, Gaston
- **Data Analysts**: Jafar, Captain Hook, Mother Gothel, Evil Queen
- **Platform**: Hades, Shan Yu, Syndrome, Gothel
- **DevOps**: Cruella (if she codes), Horned King

Feel free to suggest more! 😄

---

## Next Steps

1. ✅ Set environment variables
2. ✅ Run `00-Setup.ipynb`
3. ✅ Run `01-Purview-Extract.ipynb`
4. ✅ Run `02-UnifiedCatalog-Extract.ipynb`
5. ⏳ Run `03-Transform-Data.ipynb` (coming soon)
6. ⏳ Run `04-KeyVault-Validation.ipynb` (coming soon)
7. ⏳ Run `05-Load-Fabric.ipynb` (coming soon)
8. 📊 Create Power BI report
9. ✅ Approve completeness and relationships
10. 🚀 (Future) Run migration phase

---

**Questions?** Check [README.md](../README.md) for full architecture details.
