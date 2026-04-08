# PurviewMigration Backlog

Date: 2026-04-08

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
