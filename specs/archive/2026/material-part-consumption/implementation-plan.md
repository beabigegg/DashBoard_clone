---
change-id: material-part-consumption
schema-version: 0.1.0
last-changed: 2026-05-20
---

# Implementation Plan: material-part-consumption

## Objective
Ship a complete read-only report page `/material-consumption` ("料號用量報表") as one
non-atomic vertical slice: a new Flask Blueprint + service + SQL + dedicated RQ worker
backed by a two-layer Redis+Parquet-spool+DuckDB pipeline, plus a new Vue3 SPA bundle
registered in portal-shell drawer-2. One Oracle query family against
`DW_MES_LOTMATERIALSHISTORY` (joined to `DWH.DW_MES_CONTAINER.PJ_TYPE`) produces a tiny
day-level **summary spool** (regrouped to week/month/quarter in DuckDB with no Oracle
re-query) and a **detail spool** (raw rows, paginated + chunked CSV, async via the new
`material-consumption` RQ queue above `SYNC_ROW_LIMIT`). All AC-1..AC-8 in
`change-classification.md` must pass.

## Execution Scope

### In Scope
- Backend: new route blueprint, service, DuckDB runtime, SQL files, RQ job function.
- Two spools (summary + detail) per `design.md §Parquet Schema` / `data-shape-contract.md §3.9`.
- 7 endpoints per `api-contract.md` line 305 and `design.md §API Surface`.
- Business rules MC-01..MC-04 enforcement (`business-rules.md` lines 221-224).
- `rq_monitor_service._QUEUE_NAMES` additive update for the new queue.
- Frontend: new `frontend/src/material-consumption/` app with FilterPanel, TrendChart
  (echarts), KPI cards, TYPE breakdown chart, detail table; scoped `.theme-material-consumption` CSS.
- Registration: `data/page_status.json` (drawer-2), `asset_readiness_manifest.json`,
  `route_scope_matrix.json`, `routes/__init__.py`, `routeContracts.js`.
- New systemd worker unit + watchdog under `deploy/`.
- Tests per `test-plan.md` (Tier 0/1 pre-merge; Tier 3/4 nightly/weekly).

### Out of Scope
- DuckDB prewarm (MC-05 — intentionally absent; no test).
- Any DB migration — read-only Oracle access only.
- Changes to existing endpoints, existing spool schemas, or existing report pages.
- Modifying any `frontend/src/shared-ui/` emit/prop surface non-additively.
- Soak/stress execution pre-merge (nightly Tier 3 / weekly Tier 4 only).
- Authoring `design.md` — owned by `spec-architect`, already complete.
- Date-range guardrails / 5s aggregate tuning beyond defensive 20-part cap (open risk; revisit in stress).

## Required Changes
| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | backend route | NEW `routes/material_consumption_routes.py` — 7 endpoints, `success_response` envelope, per-kwarg forwarding | backend-engineer |
| IP-2 | backend service | NEW `services/material_consumption_service.py` — Oracle aggregate → summary+detail spool, cache keys (summary key EXCLUDES granularity per ADR-0001), input validation (MC-02), sync/async threshold (MC-04), RQ job fn | backend-engineer |
| IP-3 | backend DuckDB | NEW `services/material_consumption_duckdb_runtime.py` — summary regroup by granularity (MC-01 bucket exprs), detail pagination, chunked CSV export | backend-engineer |
| IP-4 | backend SQL | NEW `sql/material_consumption/{summary_by_day,detail_rows,filter_options}.sql` — PJ_TYPE join | backend-engineer |
| IP-5 | backend registration | MODIFY `routes/__init__.py` (import + register_blueprint + `__all__`) | backend-engineer |
| IP-6 | admin monitor | MODIFY `services/rq_monitor_service.py` — add queue name to `_QUEUE_NAMES` (additive) | backend-engineer |
| IP-7 | startup manifests | MODIFY `data/page_status.json`, `asset_readiness_manifest.json`, `route_scope_matrix.json` | backend-engineer |
| IP-8 | deploy | NEW systemd worker unit + watchdog under `deploy/` for `material-consumption` queue | backend-engineer |
| IP-9 | backend tests | Write failing tests FIRST per `test-plan.md` test families (service, routes, fuzz, modernization-policy extend) | backend-engineer |
| IP-10 | frontend app | NEW `frontend/src/material-consumption/` — Vue3 app + 5 components + composable + scoped CSS | frontend-engineer |
| IP-11 | frontend registration | MODIFY `portal-shell/routeContracts.js` — add contract + in-scope list entry | frontend-engineer |
| IP-12 | frontend tests | Write failing Vitest + Playwright specs FIRST per `test-plan.md` | frontend-engineer |
| IP-13 | CI path filter | MODIFY `.github/workflows/backend-tests.yml` — add `workers/**` + `sql/**` to PR paths filter | backend-engineer |

## Source Artifact Pointers
| source | relevant pointer | used for |
|---|---|---|
| change-classification.md | AC-1..AC-8 (lines 79-86), Tier 1, high risk | acceptance criteria + scope |
| design.md | §Affected Components (lines 8-21), §Key Decisions, §Parquet Schema, §API Surface, ADR-0001 | architecture constraints, file map |
| test-plan.md | §Test Files and Named Tests (lines 39-105), §Notes (lines 114-119) | tests to write FIRST |
| ci-gates.md | §Required Gates (lines 11-25), §Promotion Policy, §Rollback Policy | verification commands |
| api-contract.md | line 305 (Material-Consumption endpoints, payload shapes) | endpoint request/response shapes |
| data-shape-contract.md | §3.9.1 summary spool, §3.9.2 detail spool | parquet column schema |
| business-rules.md | MC-01 (line 221), MC-02 (222), MC-03 (223), MC-04 (224), MC-05 (225) | aggregation/validation/threshold rules |
| CER-001 (manifest lines 159-166) | material_trace_service.py, material_trace_duckdb_runtime.py, resource_history_sql_runtime.py | reuse patterns |
| CER-002 (manifest lines 167-171) | rq_monitor_service.py | `_QUEUE_NAMES` edit target |
| CER-003 (manifest 173-177) | DWH.DW_MES_CONTAINER.PJ_TYPE (VARCHAR2) confirmed | TYPE column in SQL JOIN |

## File-Level Plan
| path or glob | action | notes |
|---|---|---|
| `src/mes_dashboard/routes/material_consumption_routes.py` | create | 7 endpoints; per-kwarg forwarding; 400 VALIDATION_ERROR / 410 CACHE_EXPIRED |
| `src/mes_dashboard/services/material_consumption_service.py` | create | Oracle→spool, MC-02 validation, MC-04 threshold, RQ job fn; summary key excludes granularity |
| `src/mes_dashboard/services/material_consumption_duckdb_runtime.py` | create | regroup (MC-01 exprs), pagination, chunked CSV |
| `src/mes_dashboard/sql/material_consumption/summary_by_day.sql` | create | day-level aggregate + PJ_TYPE join |
| `src/mes_dashboard/sql/material_consumption/detail_rows.sql` | create | raw rows + pj_type |
| `src/mes_dashboard/sql/material_consumption/filter_options.sql` | create | distinct filter values |
| `src/mes_dashboard/routes/__init__.py` | modify | import + register_blueprint + `__all__` |
| `src/mes_dashboard/services/rq_monitor_service.py` | modify | add queue name to `_QUEUE_NAMES` (additive) |
| `data/page_status.json` | modify | add `/material-consumption` page object (drawer-2) |
| `docs/migration/full-modernization-architecture-blueprint/asset_readiness_manifest.json` | modify | map `/material-consumption` → actual dist asset filename |
| `docs/migration/full-modernization-architecture-blueprint/route_scope_matrix.json` | modify | classify `/material-consumption` in-scope |
| `deploy/` (systemd unit + watchdog) | create | `material-consumption` worker process + watchdog |
| `.github/workflows/backend-tests.yml` | modify | add `workers/**` + `sql/**` to PR paths filter |
| `frontend/src/material-consumption/` | create | Vue3 app, 5 components, `useConsumptionQuery.ts`, scoped `style.css` |
| `frontend/src/portal-shell/routeContracts.js` | modify | route contract + in-scope entry |
| `tests/test_material_consumption_service.py` | create | Tier 0 unit; both Oracle + spool paths per kwarg |
| `tests/test_material_consumption_routes.py` | create | Tier 0-1 route forwarding + rq_monitor |
| `tests/routes/test_fuzz_routes.py` | modify | extend with MC-02 meta-char/wildcard cases |
| `tests/test_modernization_policy_hardening.py` | modify | extend AC-8 asset-readiness + page_status assertions |
| `tests/stress/test_material_consumption_stress.py` | create | Tier 3 nightly; `@pytest.mark.stress` |
| `frontend/src/material-consumption/__tests__/*.test.ts` | create | Vitest unit (TrendChart, useConsumptionQuery, FilterPanel) |
| `frontend/tests/playwright/material-consumption{,-resilience,-data-boundary}.spec.ts` | create | E2E / resilience / data-boundary |

## Backend Work Packet (backend-engineer)

### TDD order (write failing tests FIRST, then implement)
1. `tests/test_material_consumption_service.py` (Tier 0) — all named tests in `test-plan.md` lines 57-74.
2. `tests/test_material_consumption_routes.py` (Tier 0-1) — named tests lines 41-55.
3. Extend `tests/routes/test_fuzz_routes.py` — SQL meta-char + wildcard tokens (MC-02).
4. Extend `tests/test_modernization_policy_hardening.py` — AC-8 asset-readiness + `page_status.json` assertions (do NOT duplicate the fixture).
5. `tests/stress/test_material_consumption_stress.py` (Tier 3 nightly) — file auto-discovered; mark `@pytest.mark.stress`.
6. Implement IP-1..IP-8, IP-13 until all the above pass.

### Reuse patterns (CER-001 approved references)
- Spool execute + idempotency-check-before-write: `material_trace_service.execute_to_spool()` / `get_spool_file_path()`.
- Detail pagination + chunked CSV: `material_trace_duckdb_runtime.py`.
- Granularity bucket regroup: `resource_history_sql_runtime._granularity_bucket_expr`.

### New files
- `routes/material_consumption_routes.py` — Blueprint `material_consumption_bp`; 7 routes
  matching `design.md §API Surface` and `api-contract.md` line 305. Each route reads request
  params via `args.get(...)` / body and forwards them per-kwarg to the service. Validation
  errors (MC-02) return 400 `VALIDATION_ERROR`; spool miss returns 410 `CACHE_EXPIRED`.
- `services/material_consumption_service.py` — functions: filter-options, summary query
  (Oracle aggregate → summary spool, always sync), detail query (sync ≤ `SYNC_ROW_LIMIT`
  default 30000, else enqueue RQ job on `material-consumption`), input validation/wildcard
  translation (MC-02), RQ job entry fn. **Idempotent spool write**: check
  `get_spool_file_path()` exists before Oracle execute. Summary cache key MUST EXCLUDE
  granularity (ADR-0001, MC-03).
- `services/material_consumption_duckdb_runtime.py` — summary regroup with granularity
  bucket exprs (MC-01: `date_trunc('week',...)`, `strftime(...,'%Y-%m')`, quarter expr);
  detail pagination + chunked CSV stream.
- `sql/material_consumption/summary_by_day.sql` — day-level aggregate of `QTYCONSUMED`/
  `QTYREQUIRED` over `TRUNC(TXNDATE)`, JOIN `DWH.DW_MES_CONTAINER.PJ_TYPE` (MC-01).
- `sql/material_consumption/detail_rows.sql` — raw rows + `PJ_TYPE` (detail spool schema, §3.9.2).
- `sql/material_consumption/filter_options.sql` — distinct `workcenter_groups`, `primary_categories`, `pj_types`.

### Files to modify
- `routes/__init__.py` — import `material_consumption_bp`, `register_blueprint(...)`, add to `__all__`.
- `services/rq_monitor_service.py` — add `os.getenv("MATERIAL_CONSUMPTION_WORKER_QUEUE","material-consumption")` to `_QUEUE_NAMES` (module-level edit; additive).
- `.github/workflows/backend-tests.yml` — add `src/mes_dashboard/workers/**` and `src/mes_dashboard/sql/**` to `pull_request.paths` (ci-gates.md §CI/CD Workflow).

### Parquet schema (write exactly per data-shape-contract.md §3.9 — breaking-change surface)
- Summary: `txn_date DATE, material_part VARCHAR, pj_type VARCHAR, primary_category VARCHAR, total_consumed FLOAT, total_required FLOAT, lot_count INT, workorder_count INT`.
- Detail: `material_trace/forward_by_lot.sql` output columns + `pj_type VARCHAR`.

## Frontend Work Packet (frontend-engineer)

### TDD order (write failing tests FIRST)
1. `frontend/src/material-consumption/__tests__/{TrendChart,useConsumptionQuery,FilterPanel}.test.ts` — named tests `test-plan.md` lines 76-82.
2. `frontend/tests/playwright/material-consumption.spec.ts` (lines 84-90), `-resilience.spec.ts` (92-95), `-data-boundary.spec.ts` (97-101).
3. Implement IP-10, IP-11 until green.

### New files (folder `frontend/src/material-consumption/`)
- `main.ts` entry, app root component, router/store wiring consistent with sibling feature apps.
- Components: `FilterPanel.vue` (uses shared `MultiSelect`), `TrendChart.vue` (echarts line, one
  series per `material_part`, hard cap 20 series — AC-2), KPI summary cards (reuse `shared-ui`
  `SummaryCard`), `TypeBreakdownChart.vue` (echarts, BY-TYPE — AC-4), detail table
  (reuse `shared-ui` `DataTable`).
- Composable `useConsumptionQuery.ts` — submit query, poll async detail job to done, reset on
  new submit, granularity switch calls `GET /view?query_id&granularity` (NO new POST /query — AC-3, MC-03).
- `style.css` — ALL rules prefixed `.theme-material-consumption` (CSS Rule 6).

### Files to modify
- `portal-shell/routeContracts.js` — add `/material-consumption` route contract + in-scope list entry.

### echarts pattern
- TrendChart: line series, one per `material_part`, capped at 20; emit granularity-change event
  that triggers the `/view` regroup call, NOT a query reload (TrendChart test line 79). Annotate
  echarts formatter/tooltip callback params with `// TODO: type echarts callback` (CLAUDE.md TS note).

### CSS scoping
- Every top-level rule in `material-consumption/style.css` MUST be scoped under
  `.theme-material-consumption` — `npm run css:check` Rule 6 fails the build otherwise (AC-8).
- Source CSS fixes require `cd frontend && npm run build` to take effect (Flask serves from `static/dist/`).

## Registration Files (shared — explicit ownership)
| file | owner | action |
|---|---|---|
| `data/page_status.json` | backend-engineer | add `/material-consumption` page object under drawer-2 (歷史報表) |
| `asset_readiness_manifest.json` | backend-engineer | add `/material-consumption` → its dist asset; entry MUST match the actual built dist filename (vite emits hashed names) |
| `route_scope_matrix.json` | backend-engineer | classify `/material-consumption` in-scope |
| `src/mes_dashboard/routes/__init__.py` | backend-engineer | register blueprint |
| `frontend/src/portal-shell/routeContracts.js` | frontend-engineer | add route contract + in-scope entry |

Sequencing note: the `asset_readiness_manifest.json` entry must reference the dist asset that
`npm run build` actually produces. Backend-engineer should set/verify this value after
frontend-engineer's build emits the bundle, or coordinate the exact filename — a mismatch
crashes gunicorn at startup (`app.py:_validate_in_scope_asset_readiness()`, CLAUDE.md Modernization Policy).

## Contract Updates
- API: implement to `contracts/api/api-contract.md` line 305 (7 endpoints, payload shapes); already authored — match exactly, do not edit.
- CSS/UI: `.theme-material-consumption` scope per `contracts/css/css-contract.md`; verified by `npm run css:check`.
- Env: `SYNC_ROW_LIMIT` (default 30000) + `MATERIAL_CONSUMPTION_WORKER_QUEUE` (default `material-consumption`) — env-configurable, no contract change.
- Data shape: `contracts/data/data-shape-contract.md §3.9.1/§3.9.2` — already authored; match parquet schema exactly.
- Business logic: `contracts/business/business-rules.md` MC-01..MC-05 — already authored; implement to spec.
- CI/CD: `contracts/ci/ci-gate-contract.md §material-part-consumption` worker gate; ci-gates.md §CI/CD Workflow path-filter addition.

## Test Execution Plan
| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 aggregation + route forwarding | `pytest tests/test_material_consumption_service.py::TestSummaryOraclePath tests/test_material_consumption_routes.py::TestQuerySubmit -x` | aggregates QTYCONSUMED/QTYREQUIRED by TXNDATE; route forwards `material_parts`/date kwargs non-default |
| AC-2 trend series + cap | `cd frontend && npx vitest run src/material-consumption/__tests__/TrendChart.test.ts` | one series per part; caps at 20 |
| AC-3 granularity no re-query (MC-03) | `pytest tests/test_material_consumption_service.py::TestSummarySpoolPath -x`; `npx playwright test ...material-consumption.spec.ts -g granularity` | week/month/quarter regroup from spool; no new Oracle/POST query call |
| AC-4 PJ_TYPE join + kwarg | `pytest tests/test_material_consumption_service.py::TestSummaryOraclePath::test_pj_type_join_filters_correctly tests/test_material_consumption_routes.py::TestDetailSubmit::test_forwards_pj_types_kwarg_non_default -x` | PJ_TYPE join filters; `pj_types` forwarded |
| AC-5 sync/async threshold (MC-04) | `pytest tests/test_material_consumption_service.py::TestDetailOraclePath tests/test_material_consumption_routes.py::TestDetailSubmit -x` | ≤ limit inline 200; > limit enqueues RQ job 202 |
| AC-6 CSV chunked | `pytest tests/test_material_consumption_service.py::TestCsvExport -x`; playwright `test_csv_export_download_starts` | streams chunks, no full-memory load |
| AC-7 RQ queue in monitor | `pytest tests/test_material_consumption_routes.py::TestRqMonitor -x` | queue name present in `_QUEUE_NAMES` |
| AC-8 registration + CSS + startup | `cd frontend && npm run css:check`; `pytest tests/test_modernization_policy_hardening.py -x`; playwright drawer/CSS specs | scoped CSS passes; asset-readiness + page_status assertions pass |
| Tier 1 gate bundle | per ci-gates.md lines 14-21 | all required PR gates green |

## Handoff Constraints
- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the Source Artifact Pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the File-Level Plan; new paths require an approved Context Expansion Request in `context-manifest.md`.
- Tests are written FIRST (failing) before implementation per Required Changes IP-9/IP-12 (CLAUDE.md Test Coverage Discipline).
- Use `mock.assert_called_once()` + per-kwarg `call_args.kwargs[k] == v`; NEVER `assert_called_once_with(...)` (test-plan.md §Notes; CLAUDE.md).
- Test BOTH Oracle fallback AND spool/regroup paths per kwarg; fixtures must include `pj_type`, `material_part`, date columns (no silent no-op).
- Section-6 tasks in `tasks.yml` must not stay `pending` before pre-commit gate (CLAUDE.md CDD note).

## Known Risks
- `DW_MES_LOTMATERIALSHISTORY` ~17.8M rows: summary aggregate must stay ≤ 5s or "always-sync summary" breaks — validate in stress (test-plan.md `test_summary_aggregate_large_table_under_5s`); backend should defensively reject > 20 `material_parts` (MC-02).
- Parquet schema is a breaking-change surface — any future column rename/add/remove orphans files; rollback runbook MUST `rm -f tmp/query_spool/material_consumption/*.parquet` (ci-gates.md §Rollback step 3).
- `asset_readiness_manifest.json` entry not matching the actual dist filename crashes gunicorn at startup — coordinate exact built filename between engineers (CLAUDE.md Modernization Policy).
- `material-consumption` worker unit absent at deploy = detail async jobs hang; watchdog + Admin RQ monitor must alert on zero-worker-for-queue (AC-7, design §Open Risks).
- `rq_monitor_service` imports `get_redis_client` at module level — perf-detail/monitor tests running after a Redis-enabled test must stub at the service boundary (CLAUDE.md Admin Service Test Isolation).
- `MultiSelect` is shared by 12 apps — any change to it must be additive and preserve focus-return on close (CLAUDE.md Shared UI + Accessibility notes); prefer consuming it unchanged.
