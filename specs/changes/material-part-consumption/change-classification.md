# Change Classification

## Change Types
- primary: `feature-add` (new standalone report page, full vertical slice)
- secondary: `api-only-change`, `ui-only-change`, `data-shape-change`, `ci-cd-change`

## Risk Level
- high

Rationale: queries DW_MES_LOTMATERIALSHISTORY (~17.8M-row Oracle table) with multi-part wildcard input; introduces a new RQ async queue + worker process; a new two-layer Redis+Parquet-spool+DuckDB cache pipeline; a new Flask Blueprint; a new SPA bundle loaded by portal-shell; and startup-validated registration manifests (asset_readiness_manifest.json crash-risk per CLAUDE.md Modernization Policy).

## Impact Radius
- cross-module

Touches backend routes/services/sql/workers, frontend SPA + portal-shell registry, contracts (api/css/ci/data/business), admin-dashboard monitoring, deploy systemd units, and startup-validated JSON manifests.

## Tier
- 1

Additive new page; no existing endpoint, spool schema, or business rule changed. Architecture review required.

## Architecture Review Required
- yes
- reason: New data-flow pipeline (Oracle aggregate → day-level summary spool → DuckDB re-group on granularity switch; separate raw-detail spool → DuckDB runtime → async RQ → chunked CSV export). Non-obvious decisions: summary-vs-detail spool split, granularity-switch-without-Oracle-requery contract, spool parquet schema + cleanup runbook, new RQ queue + worker lifecycle + admin-monitor wiring, multi-worker spool-write concurrency, and unresolved DW_MES_CONTAINER TYPE column (DESCRIBE required before SQL written).

## Required Artifacts

Always required: `change-request.md`, `change-classification.md`, `implementation-plan.md`, `test-plan.md`, `ci-gates.md`, `tasks.yml`, `context-manifest.md`

## Optional Artifacts (default: no — set yes only with explicit reason)

| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | Net-new page; no existing behavior to characterize |
| proposal.md | no | Product decision already settled in change-request interactive clarifications |
| spec.md | no | Endpoint/payload/granularity behavior fits in design.md + api-contract + implementation-plan |
| design.md | **yes** | Architecture Review Required = yes |
| qa-report.md | no | Use agent-log/*.yml pointers unless blocking findings |
| regression-report.md | no | Additive feature; no existing behavior changed |
| visual-review-report.md | no | Evidence via agent-log/ui-ux-reviewer.yml unless screenshots are blocking |
| monkey-test-report.md | no | Cover via test-plan; durable report not required unless blocking findings |
| stress-soak-report.md | no | Stress/soak run nightly/weekly; not pre-merge |

## Required Contracts
- API: yes — new endpoints (query submit, GET /view?query_id&granularity, detail, async job status, CSV export)
- CSS/UI: yes — new `.theme-material-consumption` scope; CSS governance Rule 6 enforced by css:check
- Env: no — reuses existing Oracle/Redis/spool config (raise CER if queue name needs env knob)
- Data shape: yes — summary-spool parquet schema + detail-spool schema + endpoint JSON payloads
- Business logic: yes — consumption aggregation semantics (QTYCONSUMED/QTYREQUIRED over TXNDATE, granularity GROUP BY, BY TYPE join, multi-part wildcard, 20-series cap)
- CI/CD: yes — new RQ worker queue → new systemd unit + watchdog + CI gate entry

## Required Tests
- unit: yes
- contract: yes
- integration: yes (real-infra variants nightly)
- E2E: yes
- visual: yes
- data-boundary: yes
- resilience: yes
- fuzz/monkey: yes
- stress: yes (consideration; nightly/weekly per governance, not pre-merge)
- soak: yes (consideration; weekly per governance, not pre-merge)

## Required Agents
(in execution order)
1. `change-classifier` — classification + manifest draft
2. `spec-architect` — writes `design.md` (pipeline, queue lifecycle, granularity contract, parquet schema, TYPE-column resolution)
3. `contract-reviewer` — authors/updates api, css, data-shape, business, ci contracts from the design
4. `test-strategist` — writes `test-plan.md`
5. `ci-cd-gatekeeper` — writes `ci-gates.md`
6. `implementation-planner` — writes `implementation-plan.md`
7. `backend-engineer` — Blueprint, service, SQL, RQ worker, spool/DuckDB pipeline, rq_monitor_service, registration
8. `frontend-engineer` — Vue3 app, 5 components, echarts, portal-shell registration, scoped CSS
9. `contract-reviewer` — verifies contracts match implementation
10. `ui-ux-reviewer` — visual review, theme-scope isolation, accessibility
11. `qa-reviewer` — release readiness

## Inferred Acceptance Criteria
- AC-1: Submitting a query with one or more MATERIALPARTNAME values (wildcards allowed, up to 20) returns aggregated consumption (QTYCONSUMED, QTYREQUIRED) over the selected date range from DW_MES_LOTMATERIALSHISTORY grouped by TXNDATE.
- AC-2: The trend chart renders one line per MATERIALPARTNAME (max 20 series); selecting week/month/quarter granularity re-groups correctly.
- AC-3: Switching granularity after an initial query reads from the existing summary spool and re-groups in DuckDB WITHOUT issuing a new Oracle query (`GET /view?query_id&granularity`).
- AC-4: Consumption is breakable down BY TYPE via JOIN to DW_MES_CONTAINER using the resolved product-type column.
- AC-5: Detail records are paginated; large result sets are produced via an async RQ job that the frontend polls to completion.
- AC-6: CSV export streams the full detail set via DuckDB chunked streaming without loading all rows into memory at once.
- AC-7: The new RQ queue appears in Admin Dashboard rq_monitor (`_QUEUE_NAMES` updated) and is covered by a systemd worker unit + watchdog.
- AC-8: The new page registers cleanly in drawer-2; CSS is fully scoped under `.theme-material-consumption` with no bleed; gunicorn startup asset-readiness validation passes.

## Tasks Not Applicable
- not-applicable: 2.3

## Clarifications or Assumptions
- No Atomic Split: pieces share a single rollback fate (page works only as a whole)
- BLOCKER (design-time): DW_MES_CONTAINER TYPE column name unresolved; spec-architect must DESCRIBE live table before SQL written
- Spool parquet schema is breaking-change surface: ci-gates.md §Rollback must include `rm tmp/query_spool/material_consumption/*.parquet`
- Multi-worker spool-write concurrency needs a design decision (flag for spec-architect); prewarm de-scoped
- Stress/soak planned in test-plan but run nightly/weekly, not pre-merge

## Context Manifest Draft

### Affected Surfaces
- backend report module: routes + service + sql + RQ worker (new material_consumption slice)
- two-layer cache pipeline: Redis + Parquet spool + DuckDB runtime
- frontend SPA: new material-consumption Vue app + echarts components
- portal-shell registration + route contracts
- admin-dashboard RQ monitoring (rq_monitor_service._QUEUE_NAMES)
- deploy: new systemd worker unit + watchdog
- startup-validated registration manifests (gunicorn crash risk)
- contracts: api, css, data, business, ci

### Allowed Paths
- specs/changes/material-part-consumption/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/error-format.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md
- src/mes_dashboard/routes/
- src/mes_dashboard/services/
- src/mes_dashboard/sql/
- src/mes_dashboard/workers/
- src/mes_dashboard/core/
- src/mes_dashboard/config/
- src/mes_dashboard/app.py
- data/page_status.json
- docs/migration/full-modernization-architecture-blueprint/
- frontend/src/material-consumption/
- frontend/src/shared-ui/
- frontend/src/shared-composables/
- frontend/src/core/
- frontend/src/portal-shell/
- frontend/src/styles/tailwind.css
- frontend/tailwind.config.js
- frontend/vite.config.ts
- frontend/tests/
- tests/
- deploy/
- .github/workflows/

### Agent Work Packets

#### change-classifier
- specs/changes/material-part-consumption/
- specs/context/project-map.md
- specs/context/contracts-index.md

#### spec-architect
- specs/changes/material-part-consumption/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- src/mes_dashboard/services/
- src/mes_dashboard/core/
- src/mes_dashboard/sql/
- src/mes_dashboard/workers/

#### contract-reviewer
- specs/changes/material-part-consumption/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/error-format.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md

#### test-strategist
- specs/changes/material-part-consumption/
- tests/
- frontend/tests/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md

#### ci-cd-gatekeeper
- specs/changes/material-part-consumption/
- contracts/ci/ci-gate-contract.md
- .github/workflows/
- deploy/

#### implementation-planner
- specs/changes/material-part-consumption/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md

#### backend-engineer
- specs/changes/material-part-consumption/
- src/mes_dashboard/routes/
- src/mes_dashboard/services/
- src/mes_dashboard/sql/
- src/mes_dashboard/workers/
- src/mes_dashboard/core/
- src/mes_dashboard/config/
- src/mes_dashboard/app.py
- data/page_status.json
- docs/migration/full-modernization-architecture-blueprint/
- deploy/
- .github/workflows/
- tests/

#### frontend-engineer
- specs/changes/material-part-consumption/
- frontend/src/material-consumption/
- frontend/src/shared-ui/
- frontend/src/shared-composables/
- frontend/src/core/
- frontend/src/portal-shell/
- frontend/src/styles/tailwind.css
- frontend/tailwind.config.js
- frontend/vite.config.ts
- frontend/tests/

#### ui-ux-reviewer
- specs/changes/material-part-consumption/
- frontend/src/material-consumption/
- frontend/src/portal-shell/
- contracts/css/css-contract.md
- contracts/css/css-inventory.md

#### qa-reviewer
- specs/changes/material-part-consumption/
- contracts/
- tests/
- frontend/tests/
- deploy/
- .github/workflows/

### Context Expansion Requests
- request-id: CER-001
  requested_paths:
    - src/mes_dashboard/services/material_trace_service.py
    - src/mes_dashboard/services/material_trace_duckdb_runtime.py
    - src/mes_dashboard/services/resource_history_sql_runtime.py
  reason: spec-architect/backend-engineer need existing material-trace spool+DuckDB and resource-history granularity-regroup patterns as reference implementations
  status: approved

- request-id: CER-002
  requested_paths:
    - src/mes_dashboard/services/rq_monitor_service.py
  reason: backend-engineer must update hardcoded _QUEUE_NAMES list; file is under allowed src/mes_dashboard/services/
  status: approved

- request-id: CER-003
  requested_paths:
    - (live Oracle) DESCRIBE DWH.DW_MES_CONTAINER
  reason: TYPE column name unresolved (candidates DEVICENAME / PACKAGETYPENAME); spec-architect must resolve before SQL written
  status: pending — design blocker
