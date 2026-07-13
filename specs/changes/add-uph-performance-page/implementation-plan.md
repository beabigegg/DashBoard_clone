---
change-id: add-uph-performance-page
schema-version: 0.1.0
last-changed: 2026-07-13
---

# Implementation Plan: add-uph-performance-page

## Objective
Ship the net-new always-async `/uph-performance` report page (production-assist
drawer, order 3, displayName「UPH表現」) end-to-end: a `BaseChunkedDuckDBJob`
worker that extracts GDBA/GWBA UPH from `DWH.EAP_EVENT ⋈ EAP_EVENT_DETAIL`, the
7 read endpoints in `contracts/api/api-contract.md` lines 266-272, a new spool
namespace + parquet schema (data-shape §3.29), a new `UPH_PERFORMANCE_*` env
flag set, deploy/launcher wiring, and a new `frontend/src/uph-performance/` Vue
app implementing every confirmed state/control in `interaction-design.md`. All
six contracts are already updated — this change only implements against them.

## Execution Scope

### In Scope
- Pre-build read-only Oracle probe of `BondUPH`/`fHCM_UPH` (design.md §Pre-build
  exploratory probe; UPH-03) — backend-engineer's FIRST step, gates all SQL work.
- Backend: SQL template, worker, cache/spool service, view service, routes,
  spool-namespace registration, env-flag wiring, deploy unit + launcher functions,
  root `.env.example` block.
- Frontend: new Vue app + composables + scoped CSS, plus the four nav/build
  wiring touchpoints.
- Extending the 3 pre-existing regression tripwires (spool allowlist, job-registry
  count, `_APPROVED_CALLERS`) — same PR, no forked duplicate files.

### Out of Scope
- GWBK/GWMT/GPTA family support (only negative-path 400 coverage) — non-goal.
- Concurrency-knob tuning: `max_parallel` stays 3, single RQ worker process, no
  change to `HEAVY_QUERY_MAX_CONCURRENT` or worker count (design.md Open Risks;
  test-plan.md Out of Scope). Do NOT re-acquire the heavy slot inside the worker
  (base `run()` already brackets it).
- UPH scale conversion (UPH-04 forbids ×100/÷100 — raw `PARAMETER_VALUE` only).
- Threshold/alert coloring, CSV/Parquet export, summary/KPI cards, pareto chart
  (interaction-design.md §Deleted Controls — no backing endpoints/fields).
- Any edit to `contracts/*`, `docs/adr/0017`, or design.md — already authored.
- Opportunistic refactor of eap-alarm / production-achievement templates.

## Required Changes
| id | area | required action | owner agent |
|---|---|---|---|
| IP-0 | probe | Run ≤6h read-only Oracle probe confirming `BondUPH` (GDBA) and `fHCM_UPH` (GWBA) each return non-empty `PARAMETER_VALUE`; STOP-and-report if either empty (do not swap names) | backend-engineer |
| IP-1 | sql | `src/mes_dashboard/sql/uph_performance.sql` (new) — single chunk JOIN with family-conditional CASE detail predicate per ADR-0017 §Decision-1 | backend-engineer |
| IP-2 | worker | `src/mes_dashboard/workers/uph_performance_worker.py` (new) — `UphPerformanceJob(BaseChunkedDuckDBJob)`, `execute_uph_performance_unified_job`, `register_job_type`; `chunk_strategy=TIME`, `max_parallel=3`, `requires_cross_chunk_reduction=False` | backend-engineer |
| IP-3 | service | `src/mes_dashboard/services/uph_performance_cache.py` (new) — spool key + path, `_SCHEMA_VERSION=1` | backend-engineer |
| IP-4 | service | `src/mes_dashboard/services/uph_performance_service.py` (new) — DuckDB-derived trend/ranking/detail/filter-option views over the spool (mirror `eap_alarm_service.py`) | backend-engineer |
| IP-5 | routes | `src/mes_dashboard/routes/uph_performance_routes.py` (new) — 7 endpoints exactly as typed in api-contract lines 266-272 | backend-engineer |
| IP-6 | routes | Register `uph_performance` namespace in `spool_routes._ALLOWED_NAMESPACES` + extend parametrized allowlist test | backend-engineer |
| IP-7 | env | Wire `UPH_PERFORMANCE_USE_UNIFIED_JOB` / `_WORKER_QUEUE` / `_JOB_TIMEOUT_SECONDS` in BOTH gunicorn config path and worker boot path (parity); mirror env block into root `.env.example` | backend-engineer |
| IP-8 | deploy | `deploy/mes-dashboard-uph-performance-worker.service` (new) + `scripts/start_server.sh` start/stop/status functions (new) — SAME PR as worker, no `--job-execution-timeout` | backend-engineer |
| IP-9 | registry | Extend `_APPROVED_CALLERS["base_chunked_duckdb_job"]` + job-registry count/always-async tests | backend-engineer |
| IP-10 | app | Register blueprint in `src/mes_dashboard/app.py` (mirror eap-alarm/production-achievement blueprint mount) | backend-engineer |
| IP-11 | frontend | `frontend/src/uph-performance/` (new) — `App.vue` + composables + scoped `style.css` (`.theme-uph-performance`) implementing all confirmed states/controls | frontend-engineer |
| IP-12 | frontend | 4 wiring touchpoints: navigationManifest.js (production-assist drawer, order 3), route_scope_matrix.json (`in_scope`), vite.config.ts INPUT_MAP, routeContracts.js ROUTE_CONTRACTS | frontend-engineer |

## Source Artifact Pointers
| source | relevant pointer | used for |
|---|---|---|
| design.md | §Key Decisions, §Pre-build exploratory probe, §Migration/Rollback | worker/SQL/service constraints, probe-first ordering, kill-switch |
| docs/adr/0017 | §Decision 1-3 | single-template family-conditional CASE JOIN; append path; bridges in post_aggregate |
| interaction-design.md | §States, §Controls, §Consistency Commitments, §Confirmed | every frontend state/control verbatim; two-Type-selector distinction |
| contracts/api/api-contract.md | lines 266-272 (7 `/api/uph-performance/*` rows) | endpoint signatures, params, response schemas, error codes |
| contracts/data/data-shape-contract.md | §3.29 (spool parquet schema v1, invalid-data behavior) | worker parquet columns, coarse EXISTS filters, empty-state shape |
| contracts/business/business-rules.md | UPH-01..UPH-05, UPH-ASYNC | chunk cap, family scope, param mapping, no-scale, DB/WB via workcenter_groups, async-only |
| contracts/env/env-contract.md | §Worker Feature-Flag Env-Var Parity; `.env.example.template` UPH block | env-flag names, gunicorn/worker parity, root .env.example mirror |
| contracts/ci/ci-gate-contract.md | §New RQ Worker Deploy Checklist; §add-uph-performance-page Gate Compatibility Note | deploy/launcher PR-blocking requirement |
| contracts/css/css-contract.md | `.theme-uph-performance` scope; §4.6 (hide LoadingOverlay while job active) | CSS scoping, async-progress consistency |
| test-plan.md | AC→test mapping, Test Names, Test Update Contract, Ladder | tests to write/run |
| ci-gates.md | Required Gates table, Workflow Changes Applied, Promotion Policy | verification commands, playwright CI step + gate-inventory edits |

## File-Level Plan
| path or glob | action | notes |
|---|---|---|
| (Oracle read-only session) | probe | **backend-engineer FIRST**: ≤6h `LAST_UPDATE_TIME` window per docs/architecture/eap-event-uph-collection-investigation.md. Both families return data → proceed. Either empty → STOP, report `blocked` to user, do NOT swap `BondUPH`/`fHCM_UPH`, record as qa-report risk evidence. |
| src/mes_dashboard/sql/uph_performance.sql | create | Single template, placement mirrors `production_achievement.sql`. Single JOIN'd chunk query; `EAP_EVENT_DETAIL` ON-clause uses `d.PARAMETER_NAME = CASE SUBSTR(EQUIPMENT_ID,1,4) WHEN 'GDBA' THEN 'BondUPH' WHEN 'GWBA' THEN 'fHCM_UPH' END` (ADR-0017 §Decision-1 — NEVER a blanket `IN`-list). `EVENT_TYPE LIKE '%_M[60]'`, `LOT_ID IS NOT NULL`, `EQUIPMENT_ID LIKE 'GDBA%'`/`'GWBA%'` only, `LAST_UPDATE_TIME` window predicate mandatory (UPH-01/02/03). `{{ }}` placeholders for coarse filters. NO scale conversion on `PARAMETER_VALUE` (UPH-04). DB/WB NOT computed here. |
| src/mes_dashboard/workers/uph_performance_worker.py | create | `UphPerformanceJob(BaseChunkedDuckDBJob)`: `chunk_strategy=TIME` (≤6h), `max_parallel=3`, `requires_cross_chunk_reduction=False` (append path, ADR-0017 §Decision-2). `execute_uph_performance_unified_job` entry + `register_job_type(always_async=True)`. Wire `acquire_heavy_query_slot` per docs/architecture/service-patterns.md §RQ Worker Concurrency Gate — but do NOT re-acquire the slot (base `run()` already brackets `heavy_query_slot`; design.md Open Risks). `post_aggregate` = plain concat + two enrichment bridges: `LOT_ID`→`DW_MES_CONTAINER` (Package/Type, mirror `eap_alarm_worker._safe_lot_product_df`), `EQUIPMENT_ID`→`DW_MES_RESOURCE` (`OBJECTCATEGORY='ASSEMBLY'`→WORKCENTERNAME). Apply DB/WB label in post_aggregate via `workcenter_groups.get_workcenter_group(WORKCENTERNAME)[0]`, keep only `焊接_DB`/`焊接_WB` else NULL (design.md Decision-4, UPH-05 — NOT Oracle SQL, NOT prefix enumeration). |
| src/mes_dashboard/services/uph_performance_cache.py | create | `make_uph_performance_spool_key` (date range + families + workcenter_names + packages + pj_types + equipment_ids + `_SCHEMA_VERSION`, per data-shape §3.29 — ranking Type filter deliberately NOT in key), spool path, `_SCHEMA_VERSION=1`. |
| src/mes_dashboard/services/uph_performance_service.py | create | DuckDB-derived views over spool for trend/ranking/detail/filter-options; mirror `eap_alarm_service.py` view-derivation pattern (docs/architecture/service-patterns.md). Ranking sorted ascending by avg UPH, `avg_uph` NULL (not 0) for zero-sample, ranking `pj_type` axis independent of global filter. Trend missing-hour buckets → `null` (not 0). |
| src/mes_dashboard/routes/uph_performance_routes.py | create | 7 endpoints exactly per api-contract lines 266-272: POST `/spool` (202/400/500/503), GET `/spool/status`, `/filter-options`, `/product-filter-options` (500), `/trend` (group_by default `family`, 400 on unknown), `/ranking`, `/detail` (per_page ≤200). Pure-async: spool-miss + no worker → 503, no sync fallback (UPH-ASYNC). Add `uph_performance` to `spool_routes._ALLOWED_NAMESPACES`. Use `core/response.py` helpers. |
| src/mes_dashboard/app.py | edit | Register the new blueprint (mirror eap-alarm/production-achievement mount + any runtime-contract registration). |
| src/mes_dashboard/config/workcenter_groups.py | read-only | Call `get_workcenter_group()` — no edit. |
| env wiring (settings.py / gunicorn conf + worker boot) | edit | `UPH_PERFORMANCE_USE_UNIFIED_JOB` (default `on`), `_WORKER_QUEUE`, `_JOB_TIMEOUT_SECONDS` present on BOTH gunicorn and RQ-worker boot paths (frozen-at-boot parity, env-contract §Worker Feature-Flag Env-Var Parity). |
| .env.example (repo root) | edit | Add the `UPH_PERFORMANCE_*` block mirroring `contracts/env/.env.example.template` (contract-reviewer flagged this as backend-engineer's job). |
| deploy/mes-dashboard-uph-performance-worker.service | create | New systemd RQ worker unit; NO `rq worker --job-execution-timeout` (invalid under pinned rq<2.0.0). SAME PR as worker (ci-gates.md PR-blocking). |
| scripts/start_server.sh | edit | Add start/stop/status functions for the new worker (mirror existing async worker functions). SAME PR. |
| tests/test_spool_routes.py | edit | Add `uph_performance` to `test_allowed_namespaces_pass_namespace_validation` parametrize list. |
| tests/test_job_registry.py | edit | Bump `test_each_service_registers_exactly_one_job_type` count; add `test_uph_performance_registered_with_always_async_true`. |
| tests/test_query_cost_policy.py | edit | Add `uph_performance_worker` to `_APPROVED_CALLERS["base_chunked_duckdb_job"]`. |
| frontend/src/uph-performance/App.vue (+ composables, style.css) | create | New Vue app; CSS scoped under `.theme-uph-performance` (css-contract). Implement every confirmed state/control (see Frontend Constraints below). |
| frontend/src/portal-shell/navigationManifest.js | edit | production-assist drawer, `/uph-performance`, order 3, displayName「UPH表現」. |
| docs/migration/full-modernization-architecture-blueprint/route_scope_matrix.json | edit | Add `/uph-performance` to `in_scope`. |
| frontend/vite.config.ts | edit | Add `uph-performance` to INPUT_MAP (omitting blocks boot). |
| frontend/src/portal-shell/routeContracts.js | edit | Add `/uph-performance` ROUTE_CONTRACTS entry (mirror `/eap-alarm`). |
| .github/workflows/frontend-tests.yml | edit | Add `Run uph-performance e2e spec` step (mirror production-achievement-async); SAME PR as the playwright spec (ci-gates.md §Workflow Changes Applied). Owner: whoever lands the spec / ci-cd-gatekeeper. |

### Frontend Constraints (interaction-design.md — implement verbatim)
- All states from `interaction-design.md` §States (state-initial → state-job-failed).
  Empty ≠ broken: `EmptyState` for state-empty/state-initial, `ErrorBanner` for
  503/job-failed/expired (§Consistency Commitments).
- All controls from §Controls. The TWO Type selectors must be visibly distinct
  (§Consistency Commitments — "single highest-risk consistency point"):
  `ctrl-type-select-global` (feeds spool key) vs `ctrl-ranking-type-filter`
  (ranking-only, NOT in spool key, defaults none-selected — ranking stays empty
  until a Type is picked, per §Confirmed #2).
- Dedicated visible fine-filter bar (§Confirmed #4; ctrl-fine-filter auto-applies,
  no submit). Global filters require explicit 查詢 (rebuild spool key).
- Trend default `group_by=family` (§Confirmed #3); legend click toggles series
  (§Confirmed #5); null buckets render as gaps, never 0 (§Consistency Commitments).
- Empty-state wording: generic「此範圍無 UPH 資料，請放寬日期或調整篩選器」— no
  `BondUPH`/`fHCM_UPH` leak (§Confirmed #1).
- `product-filter-options` 500 → inline warning near Package/Type dropdowns,
  other filters usable (§Confirmed #6).
- Family filter shows only GDBA/GWBA (no static DB/WB gloss); per-row `db_wb_label`
  shown only in ranking when non-NULL (§Confirmed #7).
- Reuse `AsyncQueryProgress` + hide page `LoadingOverlay` while job active
  (css-contract §4.6), exactly as eap-alarm.

## Contract Updates
All already authored — reference only, do NOT re-edit:
- API: `contracts/api/api-contract.md` lines 266-272 (7 endpoints), `api-inventory.md`,
  both `contracts/openapi.json` + `contracts/api/openapi.json` (re-export via
  `cdd-kit openapi export` if any schema-version touch, per openapi-sync gate).
- CSS/UI: `.theme-uph-performance` scope in `contracts/css/css-contract.md` +
  `css-inventory.md`.
- Env: `UPH_PERFORMANCE_USE_UNIFIED_JOB` (+ `_WORKER_QUEUE`, `_JOB_TIMEOUT_SECONDS`)
  in `env-contract.md`, `env.schema.json` (enum+default), `.env.example.template`.
- Data shape: `data-shape-contract.md` §3.29 spool parquet schema v1 + invalid-data
  behavior.
- Business logic: UPH-01..UPH-05, UPH-ASYNC in `business-rules.md`.
- CI/CD: `ci-gate-contract.md` §add-uph-performance-page Gate Compatibility Note +
  §New RQ Worker Deploy Checklist.

## Test Execution Plan
Implementation agents generate evidence with `cdd-kit test run`; the gate validates
`test-evidence.yml`. Required floor every change: collect, targeted, changed-area.
Add contract (all six contracts affected) and full (CI). Full ladder + all test
names in test-plan.md — do not restate here.

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 (nav at 4 points, boot) | frontend/tests/legacy/portal-shell-navigation.test.js | drawer entry order 3, app boots |
| AC-2 (≤6h chunk, LAST_UPDATE_TIME, GDBA/GWBA-only) | tests/integration/test_uph_performance_rq_async.py | chunk window ≤6h, predicate present, family-scoped |
| AC-3 (family→PARAMETER_NAME, SEQ_ID join) | tests/test_uph_performance_sql_builder.py | mapping pinned; swap-detection test fails on regression |
| AC-4 (both bridges + workcenter_groups DB/WB) | tests/integration/test_uph_performance_rq_async.py | bridges resolve; DB/WB via workcenter_groups not prefix |
| AC-5 (always-async, heavy-slot, namespace, env parity) | tests/integration/test_uph_performance_rq_async.py | 503 no-fallback; namespace allowlisted; flag parity |
| AC-6 (filters, trend group-by, independent ranking Type, detail) | tests/contract/test_uph_performance_contract.py | response shapes match; ranking pj_type independent |
| AC-7 (deploy/launcher wiring, env/openapi sync) | tests/contract/test_uph_performance_contract.py | deploy checklist test green; openapi resolves 6 |
| AC-8 (empty-state graceful, no param-name leak) | tests/integration/test_uph_performance_data_boundary.py | empty ≠ error; generic wording, no BondUPH/fHCM_UPH |
| tripwires (extend, don't fork) | tests/test_spool_routes.py, tests/test_job_registry.py, tests/test_query_cost_policy.py | namespace/count/`_APPROVED_CALLERS` updated in same PR |

## Handoff Constraints
- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this
  plan; follow the source pointers above.
- backend-engineer's IP-0 probe is mandatory and blocking: if `BondUPH` or
  `fHCM_UPH` returns empty, STOP and report `blocked` to the user — do not swap
  parameter names, do not proceed to full build without user decision.
- Do NOT re-acquire the heavy-query slot inside the worker; do NOT touch
  concurrency knobs.
- Do NOT simplify the ADR-0017 family-conditional CASE JOIN into an `IN`-list.
- Deploy unit + launcher functions MUST land in the same PR as the worker.
- If this plan omits a required file, behavior, contract, or test, stop and report
  `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request
  is approved.

## Known Risks
- **Data availability (UPH-03):** `BondUPH`/`fHCM_UPH` recently reconfigured;
  `fHCM_UPH` (GWBA) especially may not yet collect. Probe result is durable
  qa-report/stress-soak risk evidence. Page ships even if empty (graceful
  state-empty), but user decides wait/ship-known-empty/new-change.
- **Shared 3-slot semaphore, 4th heavy consumer** on a 12M-row/24h table with
  prior >180s timeout history. Mitigated by ≤6h chunking + exact-match parameter
  predicate; flagged for stress-soak-engineer. Concurrency uplift is out of scope.
- **DB/WB NULL rate:** machines whose WORKCENTERNAME doesn't match 焊接_DB/焊接_WB
  render NULL label by design (UPH-05); high NULL rate blunts ranking adornment —
  spot-check during probe.
- **Two-Type-selector confusion** is the highest UX-consistency risk — verify the
  global vs ranking Type selectors are labeled/placed so they can never be mistaken.
- `.cdd/code-map.yml` was used to locate template files (eap_alarm_worker.py:842L,
  eap_alarm_service.py:546L, production_achievement_worker.py:268L); if agents find
  it stale for these paths, request `cdd-kit code-map` before broad source reads.
