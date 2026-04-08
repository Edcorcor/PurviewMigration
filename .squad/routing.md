# Work Routing

How to decide who handles what.

## Routing Table

| Work Type | Route To | Examples |
|-----------|----------|----------|
| Web app and portal UX | Maleficent | Sign-in flow, tenant picker, capacity dropdown, workspace create/select UI, provisioning pages |
| Fabric platform and identity | Scar | Workspace creation, capacity assignment, Spark environment publish, Entra app wiring, deployment diagnostics |
| Data pipelines and notebooks | Ursula | Purview extraction, Unified Catalog mapping, transform/load logic, data model outputs |
| Power BI model and reports | Jafar | Semantic model tables, DAX measures, relationships, dashboard visuals, refresh and sharing setup |
| GitHub operations | Hades | Frequent commits, checkpoint pushes, branch hygiene, release commit discipline |
| Code review | Hades | Review PRs, check quality, enforce commit and branch standards |
| Testing | Cruella | Write tests, find edge cases, verify notebook and API flows |
| Scope & priorities | Maleficent | Sprint focus, UI-first trade-offs, cross-role prioritization |
| Session logging | Scribe | Automatic — never needs routing |

## Issue Routing

| Label | Action | Who |
|-------|--------|-----|
| `squad` | Triage: analyze issue, assign `squad:{member}` label | Maleficent |
| `squad:{name}` | Pick up issue and complete the work | Named member |

### How Issue Assignment Works

1. When a GitHub issue gets the `squad` label, **Maleficent** triages it — analyzing content, assigning the right `squad:{member}` label, and commenting with triage notes.
2. When a `squad:{member}` label is applied, that member picks up the issue in their next session.
3. Members can reassign by removing their label and adding another member's label.
4. The `squad` label is the "inbox" — untriaged issues waiting for Lead review.

## Rules

1. **Eager by default** — spawn all agents who could usefully start work, including anticipatory downstream work.
2. **Scribe always runs** after substantial work, always as `mode: "background"`. Never blocks.
3. **Quick facts → coordinator answers directly.** Don't spawn an agent for "what port does the server run on?"
4. **When two agents could handle it**, pick the one whose domain is the primary concern.
5. **"Team, ..." → fan-out.** Spawn all relevant agents in parallel as `mode: "background"`.
6. **Anticipate downstream work.** If a feature is being built, spawn the tester to write test cases from requirements simultaneously.
7. **Issue-labeled work** — when a `squad:{member}` label is applied to an issue, route to that member. Maleficent handles all `squad` (base label) triage.
