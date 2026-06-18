---
change-id: eap-alarm-analysis
schema-version: 0.1.0
last-changed: 2026-06-18
---

# Implementation Plan: eap-alarm-analysis

## Objective

Deliver the EAP ALARM Analysis report as an additive RQ-async + DuckDB spool-read
pipeline behind a new top-level "EAP" navigation category. A coarse filter
(date range + EQP-type multi-select) enqueues an `eap-alarm-query` RQ job that runs
one Oracle `DWH.EAP_EVENT ⋈ DWH.EAP_EVENT_DETAIL` query bounded by a mandatory
`LAST_UPDATE_TIME BETWEEN` predicate, decodes AlarmCategory, and writes a 10-column
parquet into the new `eap_alarm` spool namespace. After spool, all fine filters and
all five views (filter-options, summary, Pareto, trend, detail) are computed
DuckDB-only with no Oracle re-query. Delivery satisfies AC-1..AC-8 and EA-01..EA-07,
passes all Tier-1 required gates in `ci-gates.md`, and is fully additive (zero change
to existing routes/services/spool namespaces).

The chosen approach is fixed by `design.md` (Key Decisions) and ADR-0008. Do not
re-derive architecture; this plan only sequences execution.

## Execution Scope

### In Scope
- New backend route Blueprint, service, cache/spool-meta module, and RQ worker for EAP ALARM (7 endpoints).
- `eap_alarm` namespace registration in `spool_routes._ALLOWED_NAMESPACES` + parametrized test (same PR).
- Blueprint + worker-queue wiring in `app.py`; `eap-alarm-query` in `rq_monitor_service._QUEUE_NAMES`.
- New Vue SPA `frontend/src/eap-alarm/` mirroring `reject-history` structure; coarse + fine filter UI; Pareto/trend/detail; all CSS under `.theme-eap-alarm`.
- Portal-shell new "EAP" top-level category + route/guard entry.
- Modernization manifests updated in same PR (`data/page_status.json`, `docs/migration/asset_readiness_manifest.json`, `docs/migration/route_scope_matrix.json`).
- New systemd unit `deploy/mes-dashboard-eap-alarm-worker.service`.
- All test families per `test-plan.md` (unit, contract, integration, e2e, resilience, data-boundary) + `tests/contract/response-samples.json` capture for all 7 endpoints.
- Regenerate `contracts/api/openapi.json` after `EapAlarmSpoolJobAccepted` schema lands.

### Out of Scope
- Stress / soak / monkey tests, visual snapshot regression as a pre-merge gate, real Oracle (Tier-3 nightly) — see `test-plan.md` Out of Scope.
- Export / CSV endpoint (EAP ALARM has none).
- Any sync fallback path — EAP ALARM is always-async (design.md "Always-async, no sync fallback"). Do not add a sync branch.
- Editing any existing spool namespace, parquet schema, route, or service. No opportunistic refactor of `reject-*` reference code.
- Fine-grain spool keys (per-fine-filter Oracle jobs) — explicitly rejected in design.md.
- Lazy/N+1 Oracle load of DETAIL on row expand — explicitly rejected; DETAIL is JOIN-loaded at spool time.

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | backend tests (TDD) | Write failing unit tests first: `test_eap_alarm_service.py` (spool-key, missing-date-range ValueError, AlarmCategory decode, EQP allowlist, `_SCHEMA_VERSION` pin), `test_spool_routes.py::test_eap_alarm_in_allowed_namespaces` | backend-engineer |
| IP-2 | backend service | Create `services/eap_alarm_service.py`: spool-key hashing (EA-01), LAST_UPDATE_TIME-guarded SQL builder (EA-03), EQP allowlist (EA-07), 5 DuckDB view computes (filter-options/summary/pareto/trend/detail) | backend-engineer |
| IP-3 | backend cache | Create `services/eap_alarm_cache.py`: `_SCHEMA_VERSION` int (EA-06), TTL, parquet path/meta, AlarmCategory decode map (EA-05) | backend-engineer |
| IP-4 | backend worker | Create `workers/eap_alarm_worker.py`: RQ job fn (Oracle JOIN → decode → parquet write), `register_job_type(...)` at import; Oracle connect post-fork only | backend-engineer |
| IP-5 | backend routes | Create `routes/eap_alarm_routes.py`: 7 endpoints (Type B async, no sync fallback) per api-contract rows 248–254 | backend-engineer |
| IP-6 | namespace gate | Modify `routes/spool_routes.py`: add `"eap_alarm"` to `_ALLOWED_NAMESPACES` | backend-engineer |
| IP-7 | app wiring | Modify `app.py`: register `eap_alarm_bp`; add `eap-alarm-query` to RQ queue/monitor wiring | backend-engineer |
| IP-8 | contract evidence | Capture `tests/contract/response-samples.json` for all 7 endpoints; regenerate `contracts/api/openapi.json` | backend-engineer |
| IP-9 | deploy unit | Create `deploy/mes-dashboard-eap-alarm-worker.service` mirroring reject-worker; export `EAP_ALARM_*` env set | backend-engineer |
| IP-10 | backend test phases | After backend code: `cdd-kit test run eap-alarm-analysis --phase collect`, then `--phase targeted`, then `--phase changed-area`; add `--phase contract` (API change) and `--phase quality` (css governance touched downstream) | backend-engineer |
| IP-11 | frontend SPA | Create `frontend/src/eap-alarm/` (App.vue, FilterBar, FineFilterBar, SummaryCards, ParetoChart, TrendChart, DetailTable, composables/useEapAlarmFilter.js, main.ts, style.css) under `.theme-eap-alarm` | frontend-engineer |
| IP-12 | nav shell | Modify `frontend/src/portal-shell/`: add "EAP" top-level category + "EAP ALARM 分析" route/guard | frontend-engineer |
| IP-13 | frontend tests | Write `frontend/tests/unit/eap-alarm-filter.spec.js` (`_lastCommitted` re-sync), `frontend/tests/playwright/eap-alarm.spec.js` | frontend-engineer |
| IP-14 | modernization | Update `data/page_status.json`, `docs/migration/asset_readiness_manifest.json`, `docs/migration/route_scope_matrix.json` (same PR) | frontend-engineer |
| IP-15 | CSS Rule 4.5 | Add `.theme-eap-alarm` to every `:is()` group in `frontend/src/resource-shared/styles.css`; run `npm run css:check` before submit | frontend-engineer |
| IP-16 | nav unit test | Extend `tests/test_navigation_contract.py` to assert EAP top-level category present | frontend-engineer |
| IP-17 | resilience tests | Write `tests/integration/test_eap_alarm_resilience.py` (Oracle down, Redis down, cold-spool 410, in-flight abort) | e2e-resilience-engineer |
| IP-18 | data-boundary tests | Write `tests/integration/test_eap_alarm_data_boundary.py` (malformed rows, unknown category, null DETAIL, empty LOT, large text, all-null text, zero-row) via synthetic parquet fixtures | e2e-resilience-engineer |
| IP-19 | RQ async test | Write `tests/integration/test_eap_alarm_rq_async.py` (`pytestmark = integration_real`) mirroring `test_hold_history_rq_async` | e2e-resilience-engineer |
| IP-20 | e2e | Write `tests/e2e/test_eap_alarm_e2e.py` via `GunicornHarness`; extend Playwright spec for coarse→spool→fine→render + detail-expand | e2e-resilience-engineer |

## Source Artifact Pointers

| source | relevant pointer | used for |
|---|---|---|
| change-classification.md | AC-1..AC-8, Inferred Acceptance Criteria | scope + acceptance |
| design.md | Key Decisions (coarse/fine split, JOIN-at-spool, decode-at-spool, always-async); Migration/Rollback; Open Risks | implementation constraints |
| docs/adr/0008-eap-alarm-coarse-spool-detail-join.md | JOIN-with-DETAIL + coarse/fine boundary | architecture constraint |
| test-plan.md | AC→test mapping table; Test Families; Notes | tests to write/run |
| ci-gates.md | Required Gates table; Deploy Checklist; rollback policy | verification commands |
| contracts/api/api-contract.md | rows 248–254 (7 endpoints); §7 Type B (eap_alarm always-async); `EapAlarmSpoolJobAccepted` schema | route shapes |
| contracts/data/data-shape-contract.md | §3.17 (10-col parquet + 5 response shapes) | spool schema + view JSON |
| contracts/business/business-rules.md | EA-01..EA-07; AlarmCategory Decode Table | service/worker logic |
| contracts/env/env-contract.md | §Async Worker — EAP ALARM Spool (`EAP_ALARM_*`) | env defaults + worker unit |
| src/mes_dashboard/routes/reject_history_routes.py | Type B async route reference (lines 634–905) | route pattern |
| src/mes_dashboard/services/reject_dataset_cache.py | `_CACHE_SCHEMA_VERSION`, `_make_query_id`, spool key/view pattern | cache pattern |
| src/mes_dashboard/services/reject_query_job_service.py | `register_job_type(JobTypeConfig(...))` at module import (lines 193–195) | worker registration |
| deploy/mes-dashboard-reject-worker.service | systemd unit template | deploy unit |
| frontend/src/reject-history/ | App.vue + components/ + style.css + main.ts | SPA structure |

## File-Level Plan

| path or glob | action | notes |
|---|---|---|
| src/mes_dashboard/routes/eap_alarm_routes.py | create | 7 endpoints; thin controllers; Type B async, no sync fallback |
| src/mes_dashboard/services/eap_alarm_service.py | create | spool-key (EA-01), SQL builder w/ LAST_UPDATE_TIME guard (EA-03), EQP allowlist (EA-07), 5 DuckDB views |
| src/mes_dashboard/services/eap_alarm_cache.py | create | `_SCHEMA_VERSION` (EA-06), TTL, parquet path/meta, AlarmCategory decode map (EA-05) |
| src/mes_dashboard/workers/eap_alarm_worker.py | create | RQ job fn; `register_job_type` at import; Oracle connect post-fork (ADR-0004) |
| src/mes_dashboard/routes/spool_routes.py | modify | add `"eap_alarm"` to `_ALLOWED_NAMESPACES` (line ~20–24) |
| src/mes_dashboard/app.py | modify | register `eap_alarm_bp`; wire `eap-alarm-query` queue + `rq_monitor_service._QUEUE_NAMES` |
| deploy/mes-dashboard-eap-alarm-worker.service | create | mirror reject-worker; queue default `eap-alarm-query`; export `EAP_ALARM_*` |
| frontend/src/eap-alarm/App.vue | create | top-level app; mounts FilterBar + FineFilterBar + views |
| frontend/src/eap-alarm/main.ts | create | mount entry (intentionally TS for entry; mirror reject-history/main.ts) |
| frontend/src/eap-alarm/FilterBar.vue | create | coarse: date range + eqp_type multiselect (10-value enum) |
| frontend/src/eap-alarm/FineFilterBar.vue | create | fine: alarm_text fuzzy multiselect, alarm_category multiselect, eqp_id multiselect |
| frontend/src/eap-alarm/SummaryCards.vue | create | totals per §3.17 summary shape |
| frontend/src/eap-alarm/ParetoChart.vue | create | Pareto by alarm_text; bind `@click` on `<VChart>` |
| frontend/src/eap-alarm/TrendChart.vue | create | stacked day/hour by eqp_type per §3.17 trend shape |
| frontend/src/eap-alarm/DetailTable.vue | create | paginated (per_page max 200); expandable rows show detail_params |
| frontend/src/eap-alarm/composables/useEapAlarmFilter.js | create | re-sync `_lastCommitted` from `selection` after every `fetchFilterOptions` |
| frontend/src/eap-alarm/style.css | create | all rules under `.theme-eap-alarm`; no unscoped top-level rules |
| frontend/src/portal-shell/ | modify | add "EAP" category + "EAP ALARM 分析" route/guard |
| frontend/src/resource-shared/styles.css | modify | add `.theme-eap-alarm` to every `:is()` group (css-contract rule 4.5) |
| data/page_status.json | modify | add EAP ALARM page entry (manual; never auto-added/removed) |
| docs/migration/asset_readiness_manifest.json | modify | add page (modernization policy) |
| docs/migration/route_scope_matrix.json | modify | add route scope row |
| tests/test_eap_alarm_service.py | create | unit: EA-01/03/05/06/07 |
| tests/test_spool_routes.py | modify | add `test_eap_alarm_in_allowed_namespaces` |
| tests/test_navigation_contract.py | modify | assert EAP top-level category present |
| tests/integration/test_eap_alarm_rq_async.py | create | `pytestmark = integration_real`; mirror hold-history style |
| tests/integration/test_eap_alarm_resilience.py | create | Oracle/Redis down, cold-spool 410, in-flight abort |
| tests/integration/test_eap_alarm_data_boundary.py | create | synthetic-parquet replay; null/large/unknown/empty/zero-row |
| tests/e2e/test_eap_alarm_e2e.py | create | GunicornHarness |
| tests/contract/response-samples.json | modify | add samples for all 7 endpoints |
| contracts/api/openapi.json | modify | regenerate after `EapAlarmSpoolJobAccepted` lands |
| frontend/tests/unit/eap-alarm-filter.spec.js | create | `_lastCommitted` re-sync |
| frontend/tests/playwright/eap-alarm.spec.js | create | coarse→spool→fine→render; catch-all routes FIRST, specific LAST |

## Backend Execution Packet (backend-engineer)

Execution order (TDD): IP-1 (failing tests) → IP-2..IP-7 (code) → IP-9 (deploy unit) → IP-8 (samples + openapi regen) → IP-10 (test phases).

Key constraints (do not deviate — sourced from contracts/design):
- Spool key = `eap_alarm:{date_from}:{date_to}:{sha256(sorted(','.join(sorted(eqp_types))))[:8]}` (EA-01). AlarmText/category/eqp_id NEVER in the key.
- `LAST_UPDATE_TIME BETWEEN :date_from AND :date_to` is mandatory; missing/unbounded → 400 `VALIDATION_ERROR` (EA-03). Add a guard in the SQL builder that raises `ValueError` (route maps to 400).
- Oracle SQL shape: `SELECT ... FROM DWH.EAP_EVENT e LEFT JOIN DWH.EAP_EVENT_DETAIL d ON d.SEQ_ID = e.SEQ_ID WHERE e.LAST_UPDATE_TIME BETWEEN :date_from AND :date_to AND e.EQUIPMENT_TYPE IN (...)`. `LOT_ID` is on `EAP_EVENT` (no MES lot JOIN).
- EQP type closed enum (EA-07, 10 values): `{GDBA,GCBA,GWBA,GWBK,GPRA,GTMH,GWMT,GDSD,GWAC,GPTA}`. Value outside → 400; empty list → 400.
- AlarmCategory decode (EA-05) applied at spool-load time; parquet stores BOTH `ALARM_CATEGORY_CODE` (raw int) and `ALARM_CATEGORY` (label). 9 codes (0,1,2,3,4,5,6,7,64) per business-rules.md table + any-other → `"未知"`.
- Parquet = exactly the 10 columns in data-shape §3.17; `DETAIL_PARAMS` is a JSON string of remaining EAV params (excluding AlarmText/AlarmCategory/AlarmCode columns).
- `_SCHEMA_VERSION` integer in `eap_alarm_cache.py`, participates in spool key (EA-06). Column add/remove/rename must bump it in the same commit + add parquet `rm` to rollback.
- DuckDB views (all fine-filter aware, no Oracle re-query — EA-02/EA-04): filter-options, summary, pareto (top-50, descending count, cumulative_pct), trend (day|hour × eqp_type stacked), detail (paginated, per_page max 200). Exact JSON shapes in data-shape §3.17 "Response shapes".
- Worker: `register_job_type(JobTypeConfig(...))` at module import (mirror `reject_query_job_service.py:193-195`); Oracle connections established post-fork inside the job fn, never at import (ADR-0004 / design Open Risks).
- Progress milestones 5→15→90→100 (ci-gates nightly note); EAP inner fn cannot accept per-chunk callback, so use coarse bracket milestones (cache-spool-patterns "Type B coarse bracket" rule).
- Type B only: 202 `{async, job_id, status_url, query_id}` (`EapAlarmSpoolJobAccepted`); spool-miss on fine-filter calls → 410. No sync 200 fallback branch.
- Namespace `eap_alarm` (underscore) is the spool namespace; `eap-alarm-query` (hyphen) is the RQ queue name. Keep them distinct and consistent.

## Frontend Execution Packet (frontend-engineer)

Execution order: IP-13 (filter unit test + Playwright stub) → IP-11/IP-12 (SPA + nav) → IP-15 (CSS Rule 4.5) → IP-14 (modernization) → IP-16 (nav contract test) → `npm run css:check` + `npm run test`.

Constraints:
- Mirror `frontend/src/reject-history/` structure; reuse `shared-ui` DataTable/SummaryCard/LoadingOverlay and `MultiSelect.vue` (changes to MultiSelect must be additive — grep consumers first).
- All feature CSS scoped under `.theme-eap-alarm`; any `<Teleport to="body">` content wrapped in a thin `<div class="theme-eap-alarm">` (css-contract 4.4). Add `.theme-eap-alarm` to every `:is()` group in `resource-shared/styles.css` (4.5) via `sed` batch.
- `useEapAlarmFilter.js`: after every `fetchFilterOptions`, re-sync `_lastCommitted` from `selection` (frontend-patterns snapshot-diff rule).
- Coarse submit triggers async spool + poll `status_url`; show Loading three-tier; DetailTable renders only after `query_id` is set.
- Oracle DATE/TIMESTAMP rendering: inspect H/M/S before `new Date()` to avoid ±8h TZ shift (frontend-patterns).
- Modernization (same PR): `data/page_status.json` (add entry; never auto-managed), `asset_readiness_manifest.json`, `route_scope_matrix.json`. i18n: add the EAP nav label to ALL language files (no partial update).
- Playwright spec: register catch-all routes FIRST, specific routes LAST (LIFO); `pageRendered` guard checks `.theme-eap-alarm` presence (not body length); click submit in `beforeEach` before asserting DetailTable.

## e2e-resilience Execution Packet (e2e-resilience-engineer)

Constraints:
- `tests/integration/test_eap_alarm_rq_async.py`: `pytestmark = pytest.mark.integration_real`; mirror `test_hold_history_rq_async`. Assert job dispatch, parquet write, progress 5→15→90→100, job-failure path, spool cache-hit, spool-miss 410, fine-filter per-kwarg forwarding (`call_args.kwargs[key]`, both spool-hit and spool-miss paths), and detail expansion issues NO extra Oracle query (EA-04).
- `tests/integration/test_eap_alarm_resilience.py`: Oracle-down during spool, Redis-down, cold-spool 410 on fine-filter, in-flight abort on unload.
- `tests/integration/test_eap_alarm_data_boundary.py`: DuckDB replay with synthetic parquet fixtures (no live Oracle): malformed rows, unknown category→`"未知"`, null DETAIL_PARAMS→null field, empty LOT_ID→null, large AlarmText (>500 chars), all-null ALARM_TEXT excluded from options, zero-row spool→empty state no 500. Fixtures must include every column the view filters on.
- `tests/e2e/test_eap_alarm_e2e.py`: `GunicornHarness` with `mes_dashboard:create_app()` URI, `src/` prepended to PYTHONPATH; pop `FLASK_ENV/FLASK_TESTING/PYTEST_CURRENT_TEST`, set `REDIS_ENABLED=true` before `Popen`.
- Playwright resilience specs: `page.goto(...).catch(()=>{})` + early-return guard (not `loginViaApi`/`page.request.post()`).
- `_SCHEMA_VERSION` test uses `monkeypatch.setattr()` (frozen at import; `setenv` does not work).

## Deploy Steps

1. Create `deploy/mes-dashboard-eap-alarm-worker.service` from the reject-worker template; `ExecStart` runs `rq worker "${EAP_ALARM_WORKER_QUEUE:-eap-alarm-query}"`; `ReadWritePaths` includes tmp + logs; export the full `EAP_ALARM_*` env set (worker env-var parity, env-contract §Async Worker — EAP ALARM Spool).
2. Env vars (defaults sufficient): `EAP_ALARM_WORKER_QUEUE` (default `eap-alarm-query`), `EAP_ALARM_JOB_TIMEOUT_SECONDS` (1800), `EAP_ALARM_SPOOL_TTL` (72000), `EAP_ALARM_SPOOL_DIR` (`tmp/query_spool/eap_alarm`; use absolute for Docker).
3. Start `mes-dashboard-eap-alarm-worker.service` BEFORE deploying/restarting gunicorn; enable + confirm running.
4. Verify `eap_alarm` in `spool_routes._ALLOWED_NAMESPACES` (gate `test_eap_alarm_in_allowed_namespaces`); verify Admin Dashboard shows `eap-alarm-query` queue with ≥1 live worker.
5. Spool schema change (any time): bump `_SCHEMA_VERSION` + `rm -f tmp/query_spool/eap_alarm/*.parquet` in the same commit/rollback (data-shape §3.17 breaking-change surface). Rollback order is fixed in ci-gates.md "rollback policy".

## Contract Updates

- API: `contracts/api/api-contract.md` rows 248–254 + `EapAlarmSpoolJobAccepted` schema already authored; regenerate `contracts/api/openapi.json` after backend lands; capture `tests/contract/response-samples.json` for all 7 endpoints. Update `contracts/api/api-inventory.md` if not already covering the 7 endpoints.
- CSS/UI: new authored source `frontend/src/eap-alarm/style.css` under `.theme-eap-alarm` (css-contract); register in `contracts/css/css-inventory.md`.
- Env: `contracts/env/env-contract.md` §Async Worker — EAP ALARM Spool already authored (`EAP_ALARM_*`); no further edit unless defaults change.
- Data shape: `contracts/data/data-shape-contract.md` §3.17 already authored (10-col parquet + 5 response shapes); implement to match exactly.
- Business logic: `contracts/business/business-rules.md` EA-01..EA-07 + AlarmCategory Decode Table already authored; implement to match exactly.
- CI/CD: `contracts/ci/ci-gate-contract.md` already registers `tests/playwright/eap-alarm.spec.js` (§1.3.25) and the new worker deploy unit; no new gate tiers.

## Test Execution Plan

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 | tests/test_navigation_contract.py | EAP top-level category present in navigation structure |
| AC-2 (spool-key) | tests/test_eap_alarm_service.py::test_spool_key_composition | key matches `eap_alarm:{from}:{to}:{hash8}`; same coarse filter reuses parquet |
| AC-2 (namespace) | tests/test_spool_routes.py::test_eap_alarm_in_allowed_namespaces | `eap_alarm` in `_ALLOWED_NAMESPACES` |
| AC-2 (dispatch) | tests/integration/test_eap_alarm_rq_async.py | RQ job dispatched; parquet written |
| AC-3 (guard) | tests/test_eap_alarm_service.py::test_missing_date_range_raises_value_error | ValueError when LAST_UPDATE_TIME range absent |
| AC-3 (JOIN+index) | tests/integration/test_eap_alarm_rq_async.py::TestEapAlarmWorkerFn | JOIN runs; index predicate present in SQL |
| AC-4 (fine from DuckDB) | tests/integration/test_eap_alarm_rq_async.py::TestEapAlarmSpoolCacheHit | fine-filter options derived, no Oracle re-query |
| AC-4 (410) | tests/integration/test_eap_alarm_rq_async.py::test_spool_miss_returns_410 | spool-miss → 410 CACHE_EXPIRED |
| AC-4 (re-sync) | frontend/tests/unit/eap-alarm-filter.spec.js | `_lastCommitted` re-syncs after fetchFilterOptions |
| AC-5 (decode) | tests/test_eap_alarm_service.py::test_alarm_category_decode | 9 codes mapped; unknown → "未知" |
| AC-6 (views) | tests/e2e/test_eap_alarm_e2e.py; frontend/tests/playwright/eap-alarm.spec.js | summary/pareto/trend/detail render from DuckDB |
| AC-7 (detail no extra query) | tests/integration/test_eap_alarm_rq_async.py::test_detail_no_extra_oracle_query | detail reads DETAIL_PARAMS from spool; 0 extra Oracle calls |
| AC-8 (CSS scope) | cd frontend && npm run css:check | Rule 6 pass; no unscoped leak |
| EA-06 (schema pin) | tests/test_eap_alarm_service.py::test_schema_version_is_pinned | `_SCHEMA_VERSION` constant pinned |
| EA-07 (allowlist) | tests/test_eap_alarm_service.py::test_eqp_type_allowlist | invalid value → 400; empty list → 400 |
| 7 endpoints (samples) | tests/contract/response-samples.json + cdd-kit validate --contracts | samples captured; schema resolves |
| resilience | tests/integration/test_eap_alarm_resilience.py | Oracle/Redis down + cold-spool 410 + in-flight abort handled |
| data-boundary | tests/integration/test_eap_alarm_data_boundary.py | null/large/unknown/empty/zero-row shapes no crash |

Required test phases (floor): `collect`, `targeted`, `changed-area`. Add `contract`
(API change → response-sample capture) and `quality` (css governance gate). Generate
evidence with `cdd-kit test run eap-alarm-analysis --phase <phase>`; the gate validates
`test-evidence.yml`. Full ladder lives in `test-plan.md` / `references/sdd-tdd-policy.md`.

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.
- `_ALLOWED_NAMESPACES` registration AND its parametrized test MUST land in the same PR as the first spool write, or spool reads 403/`Unknown spool namespace` in CI.
- Modernization manifests (page_status.json + 2 docs/migration JSONs) MUST land in the same PR (modernization policy).
- New files `eap_alarm_*` will not appear in `.cdd/code-map.yml` until `cdd-kit code-map` is re-run post-implementation; refresh before any downstream grounding.

## Known Risks

- Queue-name discrepancy: `ci-gates.md` Deploy Checklist step 4 shows `os.getenv("EAP_ALARM_WORKER_QUEUE", "eap-alarm")`, but `contracts/env/env-contract.md` defines the default as `eap-alarm-query`. env-contract.md is the source of truth — use `eap-alarm-query` as the default queue name everywhere (worker unit, `rq_monitor_service._QUEUE_NAMES`, app wiring). Flag the ci-gates default literal for correction.
- Worker fork-safety (design Open Risks / ADR-0004): Oracle connections must be created inside the job fn post-fork, never at module import.
- DETAIL_PARAMS JSON cardinality could bloat parquet beyond <20MB/7-day target; capture size in stress agent-log evidence.
- AlarmText fuzzy multi-select (DuckDB ILIKE over large distinct sets) is the most expensive fine-filter; verify <100ms recompute at ~385K rows.
- `.cdd/code-map.yml` does not yet include the new files (generated 2026-06-17); precise line ranges for new modules are unavailable until regen. No staleness impact on this plan since all new files are creates.
