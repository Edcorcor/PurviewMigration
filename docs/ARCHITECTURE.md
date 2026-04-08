# Architecture & Data Flows

## System Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                                                                      │
│  Azure Tenant Environment                                           │
│  ├─ Purview Data Governance (1 or more instances)                  │
│  │  ├─ Collections (Mgmt plane)                                     │
│  │  ├─ Data Sources (Scanning plane)                                │
│  │  ├─ Assets (Catalog plane)                                       │
│  │  ├─ Scans & Runtimes (Ops plane)                                 │
│  │  └─ Classifications & Business Metadata                          │
│  │                                                                   │
│  ├─ Key Vaults (Credentials mgmt)                                   │
│  │  └─ Must be wired to Fabric workspace                            │
│  │                                                                   │
│  └─ Microsoft Fabric (Workspace)                                    │
│     ├─ OneLake (Storage layer)                                      │
│     ├─ Unified Catalog (Data Products, Quality)                     │
│     └─ Lakehouse (Delta tables for audit data)                      │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘

                              ↓

┌──────────────────────────────────────────────────────────────────────┐
│  Jupyter Notebooks (PySpark ETL)                                    │
│  ├─ 00-Setup: Discover & validate                                  │
│  ├─ 01-Extract: Pull Purview metadata                              │
│  ├─ 02-Extract: Pull Fabric metadata                               │
│  ├─ 03-Transform: Normalize & deduplicate                          │
│  ├─ 04-Validate: Key Vault & Runtimes check                        │
│  └─ 05-Load: Persist to Fabric OneLake                             │
└──────────────────────────────────────────────────────────────────────┘

                              ↓

┌──────────────────────────────────────────────────────────────────────┐
│  Fabric Lakehouse (Delta Tables)                                    │
│  ├─ Bronze layer (raw): extracts/*_raw.parquet                     │
│  ├─ Silver layer (cleaned): *_silver (deduplicated, normalized)    │
│  ├─ Gold layer (report): vw_* (star schema, relationships)         │
│  └─ Metadata: _audit_runs (lineage & timestamps)                   │
└──────────────────────────────────────────────────────────────────────┘

                              ↓

┌──────────────────────────────────────────────────────────────────────┐
│  Power BI Report                                                    │
│  ├─ Data Source: Fabric Lakehouse (DirectLake or Import)          │
│  ├─ Model: Collections → Sources → Assets → Products               │
│  ├─ Visuals:                                                        │
│  │  ├─ Hierarchy tree (collections, sources, scans)               │
│  │  ├─ Coverage dashboard (% catalogued, lineage, quality)        │
│  │  ├─ Data Quality dashboard (scores, dimensions)                │
│  │  ├─ Key Vault connectivity heatmap                             │
│  │  └─ Migration readiness scorecard                              │
│  └─ Interactivity: Drill through, cross-filtering                 │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow: One Complete Cycle

### Execution: 00-Setup → 05-Load

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Setup (00-Setup.ipynb)                                       │
│    • Authenticate (Managed Identity → Service Principal)        │
│    • Discover Purview accounts in subscription                  │
│    • Select primary account (if multiple)                       │
│    • Validate Key Vault access                                  │
│    • Confirm Fabric workspace ready                             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. Purview Extract (01-Purview-Extract.ipynb)                   │
│    FOR EACH Purview account (primary + non-primary):            │
│    ├─ Collections API          → collections_raw.parquet        │
│    ├─ Data Sources API         → sources_raw.parquet            │
│    ├─ Assets API (paginated)   → assets_raw.parquet             │
│    ├─ Scans API                → scans_raw.parquet              │
│    ├─ Classifications API      → classifications_raw.parquet    │
│    ├─ Runtimes API             → runtimes_raw.parquet           │
│    └─ Tag each with source account & is_primary flag            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. Fabric Extract (02-UnifiedCatalog-Extract.ipynb)             │
│    ├─ Data Products API        → data_products_raw.parquet      │
│    ├─ Catalog Assets API       → catalog_assets_raw.parquet     │
│    ├─ Quality Scores API       → quality_scores_raw.parquet     │
│    ├─ Domains API              → domains_raw.parquet            │
│    └─ Relationship mapper (Product → Assets)                    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. Transform (03-Transform-Data.ipynb)                          │
│    ├─ Deduplicate (Purview assets across accounts)             │
│    ├─ Normalize schema (stdize field names, types)              │
│    ├─ Match entities (Purview asset ↔ Fabric product)          │
│    ├─ Build graph (lineage, ownership, classification edges)    │
│    ├─ Quality checks (orphans, nulls, cardinality)              │
│    └─ Create star schema:                                       │
│        ├─ Dimension: collections_silver                         │
│        ├─ Dimension: sources_silver                             │
│        ├─ Dimension: assets_silver                              │
│        ├─ Dimension: products_silver                            │
│        ├─ Fact: quality_scores_silver                           │
│        ├─ Fact: lineage_silver (edges)                          │
│        └─ Summary: audit_completeness_silver                    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. Key Vault Validation (04-KeyVault-Validation.ipynb)          │
│    ├─ Discover all Key Vaults in subscription                   │
│    ├─ Test access from Fabric context                           │
│    ├─ Check Fabric-linked credentials                           │
│    └─ Generate remediation playbook for disconnects             │
│        └─ key_vault_connectivity_silver.parquet                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 6. Load to Fabric (05-Load-Fabric.ipynb)                        │
│    ├─ Write all _silver tables to Lakehouse                    │
│    ├─ Partition by snapshot_date + account_source              │
│    ├─ Set table metadata & descriptions                        │
│    ├─ Register for Direct Query / Semantic Model               │
│    └─ Save immutable audit snapshot:                            │
│        ├─ audit_run_{timestamp}.json (manifest)                 │
│        ├─ audit_metrics.parquet (row counts, gaps)              │
│        └─ migration_readiness_checklist.json                    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                  ✅ Ready for Power BI Report
```

---

## Entity Relationship Model (Unified Schema)

```sql
-- After transformation, entities relate as:

Collections
  ├─ 1:many ─→ Data Sources (collection_id)
                   └─ 1:many ─→ Scans (source_id)
                                 └─ 1:many ─→ Scan Runs (scan_id)
                   └─ 1:many ─→ Assets (source_id) 
                                 ├─ 1:many ─→ Classifications (asset_id)
                                 ├─ 1:many ─→ Lineage (asset_id upstream/downstream)
                                 └─ 1:1 ─→ Data Quality Score (asset_id)
                                 
Domains
  ├─ 1:many ─→ Data Products (domain_id)
                  └─ 1:many ─→ Catalog Assets (product_id)
                               ├─ 1:1 ─→ Data Quality Score (asset_id)
                               └─ 1:many ─→ Certified Assets / Owners

Integration Runtimes
  ├─ 1:many ─→ Scans (runtime_id)

Key Vaults
  ├─ Referenced by: Data Sources (endpoint), Scans (auth)
  └─ Connectivity: 1:1 ─→ Fabric Workspace Link Status

Cross-System Mappings
  └─ Purview Asset ↔ Fabric Data Product (matched by name + lineage)
```

---

## Multi-Account Scenario

If you have **2+ Purview accounts**:

```
Subscription
├─ Purview Account A (PRIMARY)
│  ├─ Extract all collections, sources, assets
│  └─ Tag all with: source_account="AccountA", is_primary=true
│
├─ Purview Account B (Non-primary, e.g., DR)
│  ├─ Extract all collections, sources, assets
│  └─ Tag all with: source_account="AccountB", is_primary=false
│     → These become candidate Data Products in future Purview rebuild
│
└─ Unified Dataset in Fabric
   ├─ Bronze: Raw data from both accounts
   ├─ Silver: Deduplicated by asset name + type
   ├─ Gold: For PBI with domain indicator per account
   └─ Migration Plan: All AccountB assets → New Domain "DR-Imported"
```

Future Purview rebuild will:
1. Create primary domain from AccountA (main)
2. Create domain "DR-Imported" and populate with AccountB assets

---

## Configuration Precedence

```bash
# Resolved in this order:

1. Environment variables (highest priority)
   export AZURE_TENANT_ID=xxx
   export FABRIC_WORKSPACE_ID=xxx

2. Notebook widget parameters (Databricks/Synapse)
   dbutils.widgets.get("subscription_id")

3. config/environment.yml file
   azure:
     tenant_id: "${AZURE_TENANT_ID}"   ← resolves from env

4. Hard-coded defaults (lowest priority)
   DEFAULT_WORKSPACE_NAME = "PurviewAuditWorkspace"
```

---

## Incremental & Repeated Runs

To re-run after migration planning:

```python
# Setup an incremental mode (future):
execution_mode = "FULL"     # Extract everything
                # vs
execution_mode = "DELTA"    # Only changed accounts/assets since last run

# Incremental logic:
if execution_mode == "DELTA":
    last_run = load_checkpoint("audit_watermark.parquet")
    new_assets = purview.get_assets(modified_after=last_run.timestamp)
    # ... only process new/modified
    save_checkpoint(execution_params["timestamp"])
else:
    # Full refresh
    delete_checkpoint()
    # ... extract all
```

---

## Troubleshooting & Validation

### Completeness Checks
```python
# Applied in 03-Transform

# 1. Orphan Detection
orphans = assets.filter("source_id NOT IN (SELECT id FROM sources)")

# 2. Duplicate Accounting
duplicates = assets.groupby(["asset_name", "source_account"]).count().filter("count > 1")

# 3. Scan Coverage
scanned = sources.filter("has_scans == true").count()
total = sources.count()
coverage = scanned / total
# Alert if < 90%

# 4. Lineage Completeness
with_lineage = assets.filter("has_lineage == true").count()
lineage_pct = with_lineage / assets.count()
# Alert if < 70%

# 5. Quality Score Saturation
with_scores = assets.filter("asset_id IN (SELECT asset_id FROM quality_scores)").count()
quality_pct = with_scores / assets.count()
# Alert if < 50%
```

### Gap Report Output
```json
{
  "audit_run": "2026-04-08T10:45:00Z",
  "purview_coverage": {
    "total_assets": 3247,
    "with_lineage": 2105,
    "lineage_pct": 64.8,
    "status": "⚠ Below 70% threshold"
  },
  "data_quality_coverage": {
    "total_assets": 3247,
    "with_quality_score": 1623,
    "quality_pct": 49.9,
    "status": "❌ Below 50% threshold"
  },
  "key_vault_status": {
    "total_vaults": 3,
    "fabric_connected": 2,
    "needs_remediation": 1,
    "remediation_items": ["kv-prod", ...]
  },
  "multi_product_mapping": {
    "purview_assets": 3247,
    "fabric_products": 8,
    "products_with_mapped_assets": 6,
    "orphaned_products": 2
  },
  "recommendation": "Address lineage & quality gaps before migration"
}
```

---

## Performance Considerations

### Scaling Guidelines

| Metric | Local | Synapse | Fabric |
|--------|-------|---------|--------|
| Max assets/run | 50K | 500K | 2M+ |
| Memory (Spark) | 4GB | 32GB | 64GB+ |
| Runtime | 30 min | 15 min | 5 min |
| Recommended partition size | 10K rows | 100K rows | 1M rows |

For **> 1M assets**, use Delta partitioning by source_account + snapshot_date.

---

**Next**: See [QUICKSTART.md](QUICKSTART.md) for 5-minute execution guide.
