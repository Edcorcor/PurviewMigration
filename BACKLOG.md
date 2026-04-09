# PurviewMigration Backlog

Date: 2026-04-08

## Status Update

- Repository implementation completed on 2026-04-08.
- Live Fabric validation remains environment-dependent and requires working tenant permissions.

## P0 - Critical

1. Complete missing notebooks
- Owner: Ursula
- Files: notebooks/03-Transform-Data.ipynb, notebooks/04-KeyVault-Validation.ipynb, notebooks/05-Load-Fabric.ipynb
- Definition of done: All three notebooks contain runnable cells and produce expected outputs.

2. Unblock Fabric authentication for deployment
- Owner: Scar
- Files: scripts/fabric_publish.py, webapp/main.py, .env.example, config/environment.yml
- Definition of done: Provisioning works end-to-end from script and web app.

3. Build Power BI semantic model and report
- Owner: Jafar
- Inputs: notebook outputs from setup, extraction, transform, and load phases
- Definition of done: Initial publishable report with relationships, measures, and refresh plan.

## P1 - High

4. Execute full end-to-end QA pass
- Owner: Cruella
- Files: validate.py, test_system.py, test_with_credentials.py
- Definition of done: Runbook and tests pass with documented edge cases and mitigation.

5. Reconcile documentation with actual implementation
- Owner: Hades
- Files: DELIVERABLES.md, PROJECT_SUMMARY.md, README.md
- Definition of done: Docs accurately reflect notebook readiness and deployment status.

## P2 - Medium

6. Harden web app provisioning UX
- Owner: Maleficent
- Files: webapp/main.py, webapp/templates/index.html, webapp/static/app.js
- Definition of done: Clear error handling, retries, and operator-friendly status feedback.

7. Replace placeholder implementations in core clients
- Owner: Ursula
- Files: src/purview_client.py, src/key_vault_connector.py
- Definition of done: Placeholder paths removed and validated with tests.

## Suggested Next Sprint

1. Finish notebooks 03, 04, 05.
2. Configure Fabric auth and validate provisioning.
3. Deliver baseline Power BI report.
4. Run QA and align docs.

## New Backlog - Migration Orchestrator

### P0 - Must Have

1. Add run-lock validation before migration starts
- Owner: Scar
- Files: webapp/main.py, data/reports/
- Definition of done: Migration cannot start when a Purview DG run is active; lock status is visible in UI and persisted.

2. Provision Data Governance Landing Zone and target Purview
- Owner: Maleficent
- Files: webapp/main.py, scripts/
- Definition of done: App can create landing zone resources and deploy target Purview instance with idempotent reruns.

3. Migrate metadata from source Purview to target Purview
- Owner: Ursula
- Files: notebooks/, src/purview_client.py
- Definition of done: Metadata entities and relationships are copied with validation report and rerun safety.

4. Generate permissions remediation script for data sources
- Owner: Cruella
- Files: scripts/, data/reports/
- Definition of done: Script output removes old Purview MSI access and grants new Purview MSI access for impacted sources.

5. Preserve app login permissions parity
- Owner: Hades
- Files: scripts/, data/reports/
- Definition of done: Existing app logins and effective permissions are mapped from old Purview to new Purview and differences are reported.

### P1 - High Value

6. Add migration status and blockers dashboard in web app / report
- Owner: Jafar
- Files: webapp/templates/index.html, webapp/static/app.js, powerbi/report_spec.md
- Definition of done: Operators can see migration stage, failures, impacted sources, and remediation completion.

7. Automate optional Power BI publish from Fabric artifacts
- Owner: Jafar
- Files: notebooks/05-Load-Fabric.ipynb, scripts/
- Definition of done: Notebook/script can publish or refresh report assets from prebuilt template and semantic model.
