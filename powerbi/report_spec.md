# Power BI Report Specification

## Purpose
Provide a governance audit view across Purview, Fabric Unified Catalog, scan coverage, quality, and Key Vault readiness.

## Pages

### 1. Executive Overview
- KPI cards: Total Assets, Total Collections, Total Data Products, Connected Key Vaults, Average Quality Score
- Trend or distribution visuals for asset types and scan status

### 2. Collection and Source Topology
- Matrix or decomposition tree for collections and child collections
- Bar chart for sources by type
- Table for source coverage and scan counts

### 3. Asset and Product Relationships
- Table or network-style visual using relationships dataset
- Drillthrough from Data Product to associated assets
- Filters for source system, primary account, and certification status

### 4. Data Quality
- Quality score distribution by product and asset type
- Low-score exception table
- Domain-level summary if domains are present

### 5. Key Vault and Readiness
- Table of vault accessibility and Fabric connection status
- Remediation steps for not-connected vaults
- Audit readiness summary based on available curated outputs

## Core Slicers
- source_system
- source_account
- asset_type
- data_product_name
- quality_status
- fabric_connected

## Refresh
- Refresh from staged parquet or Fabric-hosted tables after notebooks 03-05 run.
- Re-run notebooks in sequence before scheduled refresh if upstream metadata changed.
