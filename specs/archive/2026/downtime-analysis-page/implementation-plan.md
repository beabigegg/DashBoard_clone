---
change-id: downtime-analysis-page
schema-version: 0.1.0
last-changed: 2026-05-29
---

# Implementation Plan: downtime-analysis-page

## Objective

Deliver a new `/downtime-analysis` page (Flask Blueprint + Vue3 feature app) that surfaces per-day downtime hours (UDT/SDT/EGT), big-category breakdown, top reasons, equipment detail, and event detail with `DW_MES_JOB` enrichment via JOBID-primary + RESOURCEID+time-overlap fallback bridge. Mirrors the resource-history architecture (route → service → spool/cache → SQL → DuckDB) with a new isolated namespace `downtime_analysis_*`.

## Execution Scope

### In Scope
- Backend: routes / service / SQL / spool-cache for 5 endpoints under `/api/downtime-analysis/*` (api-contract.md §10 lines 215-219, 346-352).
- Cross-shift event merge (design.md Decision 1, DA-02), JOBID bridge Path A / Path B with tiebreak (Decision 2, DA-03), big-category taxonomy (Decision 3 / DA-04), wait/repair hours (DA-05), `DOWNTIME_BRIDGE_VERSION` invalidation (DA-06).
- Frontend Vue3 feature app at `frontend/src/downtime-analysis/` scoped under `.theme-downtime-analysis`; portal-shell lazy registration.
- Modernization-policy JSON updates: `data/page_status.json` (drawer-2, order 6), `asset_readiness_manifest.json`, `route_scope_matrix.json`, `route_contracts.json`, plus matching assertions in `tests/test_modernization_policy_hardening.py`.
- Contract additions only (see Contract Updates).

### Out of Scope
- TBD 落差分析 (KEY IN / 切換不確實); change-request.md §Non-goals.
- OEE recompute or any change to resource-history surface.
- IT JOBID backfill execution itself (runbook documented in ci-gates.md §Rollback only).
- Any modification of existing routes, response shapes, or `resource_dataset_*` / `production_history_*` spool namespaces (additive change only).
- Stress / soak / monkey / fuzz gates (excluded per change-classification.md §Tasks Not Applicable).

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | sql | Create `src/mes_dashboard/sql/downtime_analysis/{base_events,job_bridge,big_category,top_reasons,equipment_detail,event_detail}.sql` per design.md §Affected Components. | backend-engineer |
| IP-2 | service | Create `src/mes_dashboard/services/downtime_analysis_service.py` implementing DA-01..DA-06 + `_BIG_CATEGORY_MAP` frozendict + `_match_prefix_categories` (TMTT_*). | backend-engineer |
| IP-3 | cache | Create `src/mes_dashboard/services/downtime_analysis_cache.py` (Type-A spool; namespace `downtime_analysis_dataset` / `downtime_analysis_events`; cache key includes `DOWNTIME_BRIDGE_VERSION`). Mirror `resource_dataset_cache.py`. | backend-engineer |
| IP-4 | constants | Add `DOWNTIME_BRIDGE_VERSION = "1.0.0"` to `src/mes_dashboard/config/constants.py`. | backend-engineer |
| IP-5 | route | Create `src/mes_dashboard/routes/downtime_analysis_routes.py` exposing 5 endpoints listed in api-contract.md §10. Register blueprint in `routes/__init__.py`. | backend-engineer |
| IP-6 | app factory | No direct registration in `app.py` (blueprint mounts via `register_routes`); confirm path-only. Validate runtime-contract diagnostics still pass. | backend-engineer |
| IP-7 | modernization | Update `data/page_status.json` (add `/downtime-analysis`, drawer_id=`drawer-2`, order=6), `docs/migration/full-modernization-architecture-blueprint/{asset_readiness_manifest,route_scope_matrix,route_contracts}.json`. | backend-engineer |
| IP-8 | hardening test | Extend `tests/test_modernization_policy_hardening.py` with three new asserts (test-plan.md §Test File Index). | backend-engineer |
| IP-9 | backend tests | Create `tests/test_downtime_analysis_service.py` + `tests/test_downtime_analysis_routes.py` + extend `tests/test_api_contract.py` per test-plan.md §Test File Index. | backend-engineer |
| IP-10 | e2e | Create `tests/e2e/test_downtime_analysis_e2e.py` (marker `local_e2e`) per test-plan.md. | backend-engineer |
| IP-11 | vue app scaffold | Create `frontend/src/downtime-analysis/{App.vue,main.ts,index.html,style.css}` + components (`FilterBar.vue`, `KpiCards.vue`, `DailyTrendChart.vue`, `BigCategoryChart.vue`, `TopReasonsTable.vue`, `EquipmentDetail.vue`, `EventDetail.vue`) + composables (`useFilterState.ts`, `useBigCategory.ts`, `useDowntimeData.ts`). All CSS rules MUST be prefixed `.theme-downtime-analysis` (css-contract.md rule 4.4; CLAUDE.md Portal-Shell CSS Architecture). | frontend-engineer |
| IP-12 | vite entry | Add `downtime-analysis` entry to `frontend/vite.config.ts` and `frontend/index.html`; include `"src/downtime-analysis/**/*"` in `frontend/tsconfig.json` `include`. | frontend-engineer |
| IP-13 | portal-shell | Additive entries in `frontend/src/portal-shell/{nativeModuleRegistry,routeContracts,router,sidebarState}.js` for route `/downtime-analysis` (lazy dynamic import; drawer-2 sidebar slot). | frontend-engineer |
| IP-14 | frontend tests | Create `frontend/src/downtime-analysis/__tests__/{formatDowntimeDate,useBigCategory,useFilterState,css-scope}.test.ts` + `frontend/tests/playwright/downtime-analysis.spec.js` per test-plan.md. | frontend-engineer |
| IP-15 | ci workflow | Add Playwright step to `.github/workflows/frontend-tests.yml` per ci-gates.md §Required workflow edit. | ci-cd-gatekeeper or frontend-engineer |
| IP-16 | contracts CHANGELOG | Write API, business-rules, data-shape, css-inventory entries to `contracts/CHANGELOG.md` (NOT individual contract files; CLAUDE.md cdd-kit note). | contract-reviewer (already done; backend/frontend verify only) |

## Source Artifact Pointers

| source | relevant pointer | used for |
|---|---|---|
| design.md | Decision 1 (cross-shift merge key, 60s contiguity), Decision 2 (JOBID bridge Path A/B + tiebreak), Decision 3 (spool namespace), §Big-category taxonomy | backend service + SQL implementation |
| contracts/api/api-contract.md | §10 lines 215-219, 346-352 | endpoint signatures, params, error codes |
| contracts/business/business-rules.md | DA-01..DA-06 (lines 237-242) | service-layer invariants + asserts |
| contracts/data/data-shape-contract.md | §3.12 (DowntimeKpiShape, DailyTrendRow, BigCategoryRow, TopReasonRow, EquipmentDetailRow, EventDetailRow, JobEnrichment) | response shape tests + TS types |
| contracts/css/css-contract.md | Rule 4.4 (Teleport theme wrapper) | frontend CSS scope |
| test-plan.md | §Acceptance Criteria → Test Mapping; §Fixture Discipline Requirements | test file authoring |
| ci-gates.md | §Required Gates, §Rollback Policy, §Promotion Policy | merge eligibility + deploy verification |
| src/mes_dashboard/routes/resource_history_routes.py | blueprint URL prefix pattern, spool injection helpers | route module structure |
| src/mes_dashboard/services/resource_dataset_cache.py | `execute_primary_query`, `apply_view`, spool register pattern | spool/cache module structure |
| frontend/src/resource-history/ | feature app skeleton (App.vue, main.ts, components/, style.css scope) | frontend app structure |

## File-Level Plan

| path or glob | action | notes |
|---|---|---|
| `src/mes_dashboard/sql/downtime_analysis/base_events.sql` | CREATE | E10-filtered SHIFT rows (DA-01) |
| `src/mes_dashboard/sql/downtime_analysis/job_bridge.sql` | CREATE | DW_MES_JOB join + overlap fallback candidates (DA-03) |
| `src/mes_dashboard/sql/downtime_analysis/{big_category,top_reasons,equipment_detail,event_detail}.sql` | CREATE | per-view derived aggregations |
| `src/mes_dashboard/services/downtime_analysis_service.py` | CREATE | implements DA-01..DA-06; merge key (Decision 1); bridge selection (Decision 2) |
| `src/mes_dashboard/services/downtime_analysis_cache.py` | CREATE | spool namespace `downtime_analysis_*`; cache key embeds `DOWNTIME_BRIDGE_VERSION` |
| `src/mes_dashboard/routes/downtime_analysis_routes.py` | CREATE | 5 endpoints; mirror resource-history Type-A spool pattern |
| `src/mes_dashboard/routes/__init__.py` | MODIFY | import + register `downtime_analysis_bp` |
| `src/mes_dashboard/config/constants.py` | MODIFY | add `DOWNTIME_BRIDGE_VERSION = "1.0.0"` |
| `data/page_status.json` | MODIFY | add page entry (drawer-2, order 6) |
| `docs/migration/full-modernization-architecture-blueprint/asset_readiness_manifest.json` | MODIFY | additive entry for `/downtime-analysis` → dist asset path |
| `docs/migration/full-modernization-architecture-blueprint/route_scope_matrix.json` | MODIFY | classify `/downtime-analysis` as in-scope |
| `docs/migration/full-modernization-architecture-blueprint/route_contracts.json` | MODIFY | additive contract entry |
| `tests/test_modernization_policy_hardening.py` | MODIFY | add three asserts (page_status, asset_readiness, route_scope) |
| `tests/test_downtime_analysis_service.py` | CREATE | 8 test classes per test-plan.md §Test File Index |
| `tests/test_downtime_analysis_routes.py` | CREATE | 5 route classes; per-kwarg forwarding via `call_args.kwargs[...]` |
| `tests/test_api_contract.py` | MODIFY | append 7 new shape tests (§3.12 references) |
| `tests/e2e/test_downtime_analysis_e2e.py` | CREATE | `local_e2e` marker; 2 real spool integration tests |
| `frontend/src/downtime-analysis/App.vue` | CREATE | root component; wraps content in `<div class="theme-downtime-analysis">` |
| `frontend/src/downtime-analysis/main.ts` | CREATE | Vite entry; mounts on `#app` |
| `frontend/src/downtime-analysis/index.html` | CREATE | per resource-history pattern |
| `frontend/src/downtime-analysis/style.css` | CREATE | ALL top-level rules MUST start with `.theme-downtime-analysis` (css:check Rule 6) |
| `frontend/src/downtime-analysis/components/{FilterBar,KpiCards,DailyTrendChart,BigCategoryChart,TopReasonsTable,EquipmentDetail,EventDetail}.vue` | CREATE | feature components |
| `frontend/src/downtime-analysis/composables/{useFilterState,useBigCategory,useDowntimeData}.ts` | CREATE | state + data-fetch composables |
| `frontend/src/downtime-analysis/__tests__/{formatDowntimeDate,useBigCategory,useFilterState,css-scope}.test.ts` | CREATE | per test-plan.md §Test File Index |
| `frontend/tests/playwright/downtime-analysis.spec.js` | CREATE | per test-plan.md |
| `frontend/index.html` | MODIFY | additive entry |
| `frontend/vite.config.ts` | MODIFY | additive entry under `rollupOptions.input` |
| `frontend/tsconfig.json` | MODIFY | add `"src/downtime-analysis/**/*"` to `include` |
| `frontend/src/portal-shell/nativeModuleRegistry.js` | MODIFY | additive dynamic-import entry |
| `frontend/src/portal-shell/routeContracts.js` | MODIFY | additive route contract |
| `frontend/src/portal-shell/router.js` | MODIFY | additive route definition |
| `frontend/src/portal-shell/sidebarState.js` | MODIFY | additive drawer-2 slot |
| `.github/workflows/frontend-tests.yml` | MODIFY | one Playwright step per ci-gates.md §Required workflow edit |

## Backend Execution Order

1. **SQL templates** — author `sql/downtime_analysis/*.sql` first; `base_events.sql` MUST encode `OLDSTATUSNAME IN ('UDT','SDT','EGT')` (DA-01) at the query layer (NST excluded server-side, not Python).
2. **Constants** — add `DOWNTIME_BRIDGE_VERSION = "1.0.0"` to `config/constants.py` (DA-06).
3. **Service** — `downtime_analysis_service.py`:
   - `_BIG_CATEGORY_MAP` frozendict + `_PREFIX_CATEGORIES = [("TMTT_", "檢查")]` (DA-04).
   - `_merge_cross_shift_events(df)`: sort by `(HISTORYID, OLDSTATUSNAME, OLDREASONNAME, OLDLASTSTATUSCHANGEDATE)`, walk fragments, new run when `current.OLDLASTSTATUSCHANGEDATE − prev.LASTSTATUSCHANGEDATE > 60s`. Aggregate `SUM(HOURS)`, `MIN(start)`, `MAX(end)`, `COUNT(*)` (DA-02).
   - `_bridge_jobid(events, jobs)`: Path A on `JOBID`; Path B candidate filter `RESOURCEID = HISTORYID AND start<COMPLETEDATE AND end>CREATEDATE`; tiebreak by `LEAST(end,COMPLETEDATE) − GREATEST(start,CREATEDATE)` DESC, `CREATEDATE` ASC, `JOBID` ASC; emit `match_source` ∈ `{'jobid','overlap','none'}`; `match_ambiguous = True` when next-best overlap ≥ 80% of winner (DA-03).
   - `get_filter_options`, `query_downtime_dataset`, `apply_view` — mirror `resource_dataset_cache.py` shape.
   - Filter narrowing: equipment dropdown excludes self (AC-6).
4. **Cache module** — `downtime_analysis_cache.py`:
   - `_RESOURCE_SPOOL_NAMESPACE = "downtime_analysis_dataset"` and `"downtime_analysis_events"`.
   - Spool dir `tmp/query_spool/downtime_analysis/`.
   - Cache key MUST include `DOWNTIME_BRIDGE_VERSION` (DA-06; AC-8).
   - Apply multi-worker startup lock pattern from `resource_history_duckdb_cache.py::_try_lock` if any pre-warm is added; default = no pre-warm.
5. **Routes** — `downtime_analysis_routes.py`, `url_prefix='/api/downtime-analysis'`. Endpoints per api-contract.md §10. Use `success_response`, `validation_error`, `cache_expired_error` from `core/response.py`. Each route reads kwargs via `request.args.get(...)` and forwards to service via `**kwargs` — every kwarg listed in api-contract.md MUST be forwarded.
6. **Blueprint registration** — `routes/__init__.py`: add import + `app.register_blueprint(downtime_analysis_bp)` in `register_routes`.
7. **Modernization JSON** — update all three JSONs + `data/page_status.json` atomically. Hard-code `drawer_id="drawer-2"` (must match hardening test).
8. **Tests** — order: (a) `test_downtime_analysis_service.py` (unit, DA-01..DA-06 + filter narrowing + `TestBridgeVersionCacheKey`), (b) `test_downtime_analysis_routes.py` (per-kwarg `call_args.kwargs[...]` style, both snapshot + Oracle paths), (c) `test_api_contract.py` extension (7 new shape classes), (d) `test_modernization_policy_hardening.py` (3 new asserts), (e) `tests/e2e/test_downtime_analysis_e2e.py` (`local_e2e` marker).

## Frontend Execution Order

1. **App scaffold** — `frontend/src/downtime-analysis/{App.vue,main.ts,index.html,style.css}`. Root `<template>` must wrap in `<div class="theme-downtime-analysis">` (css-contract.md rule 4.4).
2. **Vite entry** — add to `frontend/vite.config.ts` `rollupOptions.input`; add HTML reference in `frontend/index.html`; add `"src/downtime-analysis/**/*"` to `frontend/tsconfig.json` `include`.
3. **Portal-shell registration** — additive entries in `nativeModuleRegistry.js` (dynamic import path), `routeContracts.js` (route → bundle), `router.js` (route `/downtime-analysis`), `sidebarState.js` (drawer-2 slot order 6).
4. **Components** — `FilterBar.vue`, `KpiCards.vue`, `DailyTrendChart.vue`, `BigCategoryChart.vue` (8 buckets), `TopReasonsTable.vue`, `EquipmentDetail.vue`, `EventDetail.vue` (renders `match_source` badge; null JOB fields render as `—`).
5. **Composables** — `useFilterState.ts` (cross-narrow), `useBigCategory.ts` (8-bucket map mirror; fallback `其他/未分類`), `useDowntimeData.ts` (POST `/query` → GET `/view` two-phase).
6. **Date formatter** — `formatDowntimeDate(raw)` MUST inspect `T(\d{2}):(\d{2}):(\d{2})` BEFORE calling `new Date()`; when all three digit pairs are `'00'`, extract Y/M/D from string directly (CLAUDE.md Frontend Date Formatting Notes). Applies to `start_ts`, `end_ts`, `CREATEDATE`, `COMPLETEDATE`, `FIRSTCLOCKONDATE`, `LASTCLOCKOFFDATE`.
7. **Tests** — vitest unit (`formatDowntimeDate.test.ts`, `useBigCategory.test.ts`, `useFilterState.test.ts`, `css-scope.test.ts`), then Playwright `downtime-analysis.spec.js`.
8. **CI workflow edit** — add Playwright step in `.github/workflows/frontend-tests.yml` per ci-gates.md.

## Contract Updates

(All entries already authored by contract-reviewer; implementation agents verify presence only.)

- API: `contracts/api/api-contract.md` §10 lines 215-219, 346-352; `contracts/api/api-inventory.md` 5 new rows; CHANGELOG entry in `contracts/CHANGELOG.md`.
- CSS/UI: `contracts/css/css-inventory.md` registers `frontend/src/downtime-analysis/style.css` with theme `.theme-downtime-analysis`.
- Env: none.
- Data shape: `contracts/data/data-shape-contract.md` §3.12.1..§3.12.7.
- Business logic: `contracts/business/business-rules.md` DA-01..DA-06.
- CI/CD: existing gates in `contracts/ci/ci-gate-contract.md` suffice; no new gate contract row.

## Test Execution Plan

See test-plan.md §1 (AC → test mapping) and §3 (fixture discipline). Verification commands listed in ci-gates.md §Required Gates. Summary:

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 | `pytest tests/test_downtime_analysis_service.py::TestE10StatusFilter tests/test_api_contract.py::TestDowntimeSummaryShape` | NST excluded; UDT/SDT/EGT buckets correct |
| AC-2 | `pytest tests/test_downtime_analysis_service.py::TestBigCategoryMapping` | 8 buckets, TMTT_ prefix, strip(), EGT→工程, fallback其他 |
| AC-3 | `pytest tests/test_api_contract.py::TestDowntimeTopReasonsShape` | TopReasonRow shape per §3.12.4 |
| AC-4 | `pytest tests/test_downtime_analysis_service.py::TestCrossShiftMerge` | 3 fragments → 1 row, hours=14, fragment_count=3, gap>60s stays 2 |
| AC-5 | `pytest tests/test_downtime_analysis_service.py::TestJobidBridge tests/test_downtime_analysis_service.py::TestWaitRepairHours` | Path A/B/none; tiebreak; null contract |
| AC-6 | `pytest tests/test_downtime_analysis_service.py::TestFilterCrossNarrowing tests/test_downtime_analysis_routes.py` | equipment excludes self; both snapshot+Oracle paths |
| AC-7 | `pytest tests/test_modernization_policy_hardening.py::TestDowntimeAnalysisPage` + `cd frontend && npm run css:check` + Playwright spec | page_status entry; CSS Rule 6 pass; lazy load works |
| AC-8 | `pytest tests/test_downtime_analysis_service.py::TestBridgeVersionCacheKey` | bump version → different spool key; resource_dataset_* unchanged |

E2E: `pytest tests/e2e/test_downtime_analysis_e2e.py -m local_e2e -x`.
Playwright: `cd frontend && npx playwright test tests/playwright/downtime-analysis.spec.js`.

## Constraints and Gotchas

- **Oracle CHAR trailing-space (DA-04, DA-03)**: apply `str(v).strip()` at BOTH dict-build time AND per-record lookup. Pattern: `resource_cache.py::_load_package_group_lookup` / `get_package_group_name`. Applies to `OLDREASONNAME`, `HISTORYID`, `RESOURCEID`.
- **Midnight-UTC DATE (DA-05, frontend)**: any Oracle DATE column serialised as `T00:00:00` must NOT be passed to `new Date()` in non-UTC locale. Inspect raw H/M/S via regex; if all `'00'`, extract Y/M/D from string. Pattern: `material-consumption/components/DetailTable.vue::formatTxnDate`. Applies to `event_start`, `event_end`, `CREATEDATE`, `COMPLETEDATE`, `FIRSTCLOCKONDATE`, `LASTCLOCKOFFDATE`.
- **Multi-worker startup lock**: if a pre-warm is added (none required initially), use the file-lock pattern from `resource_history_duckdb_cache.py::_try_lock` / `_release_lock` to prevent concurrent Oracle warmup across gunicorn workers.
- **Spool parquet cleanup on schema change**: any PR that renames/adds/removes a column in `downtime_analysis_service.py` spool write path MUST add `rm -f tmp/query_spool/downtime_analysis/*.parquet` to deploy + rollback runbook AND update `contracts/data/data-shape-contract.md §3.12`. See ci-gates.md §Parquet schema gate.
- **Modernization JSON triple**: omitting any of `asset_readiness_manifest.json`, `route_scope_matrix.json`, `data/page_status.json` causes gunicorn startup crash or orphan sidebar entry. All three must land in the same PR with matching `drawer_id='drawer-2'`.
- **`drawer_id` hardening test**: `tests/test_modernization_policy_hardening.py::test_page_status_contains_downtime_analysis_in_drawer_2` hardcodes `drawer-2`; renaming the drawer requires renaming the test method and updating the assert (CLAUDE.md Modernization Policy Artifact Notes).
- **Portal-shell CSS bleed**: every top-level rule in `frontend/src/downtime-analysis/style.css` MUST be prefixed `.theme-downtime-analysis`. Enforced by `npm run css:check` Rule 6. `<Teleport to="body">` content must be wrapped in `<div class="theme-downtime-analysis">` (css-contract.md rule 4.4; same element cannot carry both `theme-downtime-analysis` and the component class — combined selector does not match authored descendant rules).
- **CSS build cache**: app serves from `src/mes_dashboard/static/dist/`; after any `style.css` edit run `cd frontend && npm run build` — Vite hashes filenames so stale `style.css` references become orphaned.
- **Test forwarding style**: every route → service kwarg assertion MUST use `mock_service.call_args.kwargs['<key>'] == <non-default>`, NEVER `assert_called_once_with(...)` whitelist (CLAUDE.md Test Coverage Discipline). Snapshot path AND Oracle fallback path must both be exercised per kwarg.
- **CHANGELOG location**: write contract version entries to `contracts/CHANGELOG.md` only — NEVER inside individual contract files (CLAUDE.md cdd-kit note; `ai-pipeline-upgrade` evidence).
- **CI gate names**: `ci-gates.md` must keep literal `## CI/CD Workflow`, `## Promotion Policy`, `## Rollback Policy` headers — already present; do not rename.

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.

## Known Risks

- JOBID coverage gap (~50% UDT, ~14% SDT) is product-visible until IT backfill completes; QA accepts as approved-with-risk per qa-report.md plan.
- Tiebreak `match_ambiguous` 80% threshold is judgmental; revisit after first month of production data (design.md §Open Risks).
- Cross-shift merge correctness depends on Oracle returning HOURS as a number — `_merge_cross_shift_events` must coerce defensively to avoid silent string-concat.
- `_BIG_CATEGORY_MAP` membership test (test-plan.md `TestBigCategoryMapping`) must pin every value; adding a new OLDREASONNAME without updating the map silently falls into `其他/未分類`.
- Frontend type-check gate is informational — `echarts` callback `params` may need `// TODO: type echarts callback` annotation rather than `any` (CLAUDE.md TypeScript Notes).
