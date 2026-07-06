# Service Architecture Patterns

Promoted learnings from project history — patching, filter indexes, QueryBuilder, SQL, and AI pipeline gotchas.

## downtime_analysis_service — Patch Site for load_downtime_events

**`downtime_analysis_service` uses function-body imports for `load_downtime_events` at all four call sites** (`apply_view`, `_build_equipment_detail_page`, and two others at lines 1164, 1210) — the name never exists in the service module's namespace.

- **Wrong:** `patch('mes_dashboard.services.downtime_analysis_service.load_downtime_events')` — silently has no effect
- **Correct:** `patch('mes_dashboard.services.downtime_analysis_cache.load_downtime_events')` (definition site)

Evidence: `downtime-analysis-page-redesign` — backend-engineer corrected this during TDD; verified at four call sites.

## _get_wip_search_index — Two-Path Field Addition

`_get_wip_search_index` (in `wip_service.py`) builds the in-process filter-options search index. It has two paths:
- **(a) Incremental sync** from `previous` cache
- **(b) Full-rebuild fallback** (`if index_payload is None:` block) that calls `_materialize_search_payload`

**Any new field added to the filter-options response must be appended to `index_payload` in BOTH paths:**
1. After the `_materialize_search_payload` call in the full-rebuild branch
2. Carried forward via `previous.get(...)` in the incremental branch

Adding only to a helper function that is never called from `_get_wip_search_index` will silently omit the field on every service restart.

Evidence: `wip-hold-drilldown-filters` (workflows/bops/pjFunctions).

## rq_monitor_service — Module-Level Import Patch Site

**`rq_monitor_service` imports `get_redis_client` at module level (`from x import y`).** Patching `mes_dashboard.core.redis_client.get_redis_client` at function level does NOT intercept calls made through `rq_monitor_service`.

Any performance-detail test that runs after a test with `REDIS_ENABLED=True` must additionally stub:
```python
patch('mes_dashboard.services.rq_monitor_service.get_rq_monitor_summary')
```

Real `rq.Worker` objects from a live Redis context contain non-serializable values that corrupt test output.

Evidence: `fix-admin-dashboard` — `TestPerfDetailRedisAdditiveKeys` required this stub after `TestApiLogsSqliteIncludesSynced` left Redis enabled.

## QueryBuilder — Counter-Forwarding for Two Independent IN-lists

**When a single service function needs two separate `QueryBuilder` instances** (e.g., `EQUIPMENTID IN (...)` and `WORKCENTER_GROUP IN (...)`), forward the param counter between them:

```python
# Forward counter before second builder
wg_builder._param_counter = builder._param_counter
wg_builder.add_in_condition(...)

# Merge back after
builder._param_counter = wg_builder._param_counter
builder.params.update(wg_builder.params)
```

Without this, both builders start at `p0` and Oracle raises `ORA-01006: bind variable does not exist` at runtime.

Pattern: `src/mes_dashboard/services/query_tool_service.py:2558-2567` (`equipment-rejects-by-lots`)

## _PARTIAL_NONKEY_COLS_LOT — Atomic Updates with SQL

**`query_tool_sql_runtime.py` uses `_PARTIAL_NONKEY_COLS_LOT` (a frozenset) in the QT-06 strict guard.** Any new column added to `lot_history.sql` or `equipment_lots.sql` must also be added to `_PARTIAL_NONKEY_COLS_LOT` atomically with the SQL change.

Omitting it causes the guard to silently collapse rows with divergent values for that column (data corruption, not an error).

Pin with a membership test: pattern `tests/test_query_tool_sql_runtime.py::TestPartialNonkeyColsLotContainsProductlinename`

Evidence: `add-package-detail-tables` — omitting `PRODUCTLINENAME` would have silently merged rows with different package values.

## SQL CTE — Two-Location Edits Required

**When a SQL file uses a named CTE (e.g., `ranked`) that feeds an outer final SELECT, any new column must appear in BOTH:**
1. The CTE's SELECT list
2. The outer SELECT

- Adding only to the outer SELECT → "column not found" error
- Adding only to the CTE → column silently dropped before the outer SELECT reads it

Evidence: `add-package-detail-tables` — `hold_history/list.sql`, `lot_history.sql`, and `equipment_lots.sql` all required two-location edits (CTE + outer SELECT).

## Shared CTE Builder for Cross-Function Parity

**When two functions must produce results provably reconcilable with each other** (e.g. a KPI total and the detail-list/CSV export it must sum to), factor the shared filter/CTE-building SQL into ONE builder function both call, rather than maintaining two independently-written WHERE/CTE chains — two parallel implementations of "the same" predicate will drift the first time either is edited alone. Pin with a structural test asserting both functions call the shared builder (e.g. `inspect.getsource`), not just a value-equality test.

Evidence: `yield-alert-kpi-csv-parity` — `design.md` Decision 1; `_build_alerts_filtered_cte()` in `yield_alert_sql_runtime.py`; `test_summary_and_alerts_share_the_same_cte_builder`.

## SQL-Frontend Column Gap

**SQL returning a column the frontend never renders is invisible to backend-only audits.** When auditing which columns a table surface is missing, cross-check SQL `SELECT` output against frontend template rendering — not just the backend route response. A column already present in SQL but absent from the Vue template produces no error and passes all backend tests.

Evidence: `add-package-detail-tables` — `equipment_lot_rejects.sql:52` already returned `PRODUCTLINENAME`; only the frontend template was missing the column.

## AI Pipeline — dispatch: raw_params Flag

**`raw_params`-style callables require the `dispatch: raw_params` YAML flag in `ai_functions.yaml`.** `query_production_history(raw_params: Dict)` takes a single positional dict, not keyword args. The AI pipeline's default `service_fn(**params)` dispatch silently fails — no error at import time, only fails at runtime when the LLM invokes the function.

```yaml
# ai_functions.yaml
- name: query_production_history
  dispatch: raw_params   # routes to service_fn(params) instead of service_fn(**params)
```

Pin with a dispatch adapter test (pattern: `TestProductionHistoryQueryDispatchAdapter`).

Evidence: `ai-pipeline-upgrade`.

## AI Pipeline — advance_query_state Pops _SESSION_STORE

**`advance_query_state` pops the full `_SESSION_STORE` entry on `ready_to_search`.** Any cross-turn state added to `_SESSION_STORE[conversation_id]` (e.g., `chat_history`) is silently lost on the first completed slot-filling query.

To preserve cross-turn state:
```python
# Before the pop
saved = state.get("chat_history", [])
# ... advance_query_state pops the entry ...
# Restore after
_SESSION_STORE[conversation_id] = {"chat_history": saved}
```

Pin with a two-turn integration test (pattern: `TestHistorySurvivesAdvanceQueryStatePop`).

Pattern: `ai_query_understanding.py:258-264`

Evidence: `ai-pipeline-upgrade` — chat_history evicted silently until R3 fix.

## AI Pipeline — _AI_SESSION Module-Level Patch Site

**`_AI_SESSION` in `ai_query_service.py` is a `requests.Session` object bound at module import time.** Tests that need to intercept HTTP calls from this service must patch:

```python
patch('mes_dashboard.services.ai_query_service._AI_SESSION')
```

Patching `requests.post` at function level does not intercept calls routed through the pre-bound Session object. Apply the same boundary-patch discipline to any other service that holds a module-level Session.

Evidence: `downtime-analysis-page` — `TestCallLlmText` required this correction in commit `ccb9347`.

## Route Parameter Parsing — Shared Facade (core/route_helpers.py)

**Prefer `core/route_helpers.py` over re-rolling per-route parameter parsing.**
Routes historically each defined their own `_parse_multi_param` / pagination
sanitisation with subtly different defaults and edge cases.

- `parse_multi_param(name, source=None)` — order-preserving, de-duped multi-value
  list. Handles GET repeated/CSV params (Werkzeug `MultiDict`) and POST JSON
  bodies (plain `dict`; list members verbatim, scalar strings CSV-split).
  Reference adopters: `reject_history_routes`, `yield_alert_routes`.
- `parse_pagination(source=None, *, default_per_page, max_per_page, page_key, per_page_key)`
  — `(page, per_page)` clamped to `page>=1`, `per_page in [1, max_per_page]`,
  with **silent** default fallback for missing/non-integer input. Reference
  adopter: `hold_history_routes` (GET path).

`source` defaults to `flask.request.args`; pass an explicit `MultiDict`/`dict`
to unit-test without an app context.

**Migration caveat — match behaviour before adopting.** `parse_pagination` falls
back silently on a non-integer value; routes that instead return an explicit
`validation_error` (e.g. `hold_history_routes` POST body path) must keep their
bespoke parsing rather than adopt the silent helper. Defaults/caps differ across
routes (50/200, 100/500, 200/500) — pass them per call site; do not unify the
numbers.

## RQ Worker Concurrency Gate — heavy_query_slot Wiring Requirement

**Every `execute_*_job` worker function that runs Oracle-heavy queries MUST wire `heavy_query_slot` before the owning feature flag is promoted to production.**

The `global_concurrency` semaphore (`MAX_CONCURRENT = 3`) bounds simultaneous Oracle connections from RQ workers to prevent DB exhaustion. Without wiring, flag-on workers bypass the gate entirely — the semaphore exists but is never acquired.

Wiring status — **legacy per-domain workers** (flag-off path; as of rq-semaphore-wiring):
- `execute_query_tool_job` — **wired** (guarded by `_QUERY_TOOL_CONCURRENCY_WIRED`)
- `execute_hold_history_query_job` — **wired** (guarded by `HOLD_ASYNC_ENABLED`)
- `execute_resource_history_query_job` — **wired** (guarded by `RESOURCE_ASYNC_ENABLED`)
- `execute_reject_query_job` — **wired at cache layer** (`reject_dataset_cache.execute_primary_query` acquires internally; no job-level acquire to avoid double-counting)
- `query_production_history` — **wired** (`production_history_service` acquires around `_run_oracle_to_spool`)
- `execute_wip_detail_job` — **wired** (unconditional; no routing flag)

Wiring status — **unified job core** (`*_USE_UNIFIED_JOB=on` path; as of base-job-semaphore-wiring):
- `BaseChunkedDuckDBJob.run()` — **wired centrally**: the Oracle fan-out (`_fan_out_reduction`/`_fan_out_append`) is bracketed by `heavy_query_slot(f"{namespace}:{job_id}")`. This covers **all** subclasses that do not override `run()`: `RejectHistoryJob`, `ProductionHistoryJob`, `DowntimeJob`, `EapAlarmJob`, `ResourceHistoryBaseJob`, `ResourceHistoryOeeJob`. Slot is unconditional — `run()` executes only on the flag-on path, so there is no flag-off parity concern, and the legacy acquires above live on the mutually-exclusive flag-off path (no double-count). `post_aggregate` stays OUTSIDE the slot (DuckDB-local, Oracle-phase-only per D1).
- `MaterialTraceJob.run()` — **wired in the override**: material_trace overrides `run()`, so it acquires `heavy_query_slot` itself around its Oracle fetch loop (no legacy per-domain acquire exists, so this is its only gate).

> ⚠️ Before base-job-semaphore-wiring, the unified path (EAP_ALARM/DOWNTIME/MATERIAL_TRACE `USE_UNIFIED_JOB=on` by default) bypassed the gate entirely — the legacy acquires only cover the flag-off path. Any new `BaseChunkedDuckDBJob` subclass inherits the slot automatically; a subclass that overrides `run()` MUST wire the slot itself (see MaterialTraceJob).

Stress/integration evidence for this wiring: `docs/architecture/base-job-semaphore-wiring-stress-soak-report.md` (`tests/stress/test_base_job_semaphore_stress.py`, `tests/integration/test_base_job_semaphore_wiring.py`).

Use the `heavy_query_slot(owner)` contextmanager from `global_concurrency` — it wraps
`acquire_heavy_query_slot` / `release_heavy_query_slot` with an exception-safe
try/finally and guards release with `if acquired` (fail-open never double-releases):

```python
from mes_dashboard.core.global_concurrency import heavy_query_slot

_slot_owner = f"{job_type}:{job_id}"
with heavy_query_slot(_slot_owner):
    result = execute_primary_query(...)
# ensure_canonical_spool and complete_job stay OUTSIDE the slot (single-acquire, D3)
```

Guard the `with heavy_query_slot(...)` call with the module-level feature flag so the
flag-off path is byte-for-byte identical (AC-5 / rq-semaphore-wiring):

```python
with (heavy_query_slot(_slot_owner) if FEATURE_ASYNC_ENABLED else nullcontext()):
    result = execute_primary_query(...)
```

Pre-production checklist before flipping any `*_USE_RQ=on`:
1. Wire `heavy_query_slot` in the owning `execute_*_job` (guarded by the feature flag).
2. Run real-Oracle load test to confirm `peak_concurrent ≤ MAX_CONCURRENT`.
3. Update stress-soak-report.md with real evidence (mock structural proof alone is insufficient).
4. For resource worker: validate DBA headroom as `HEAVY_QUERY_MAX_CONCURRENT × 2 + overhead`
   (resource fans base+OEE over `ThreadPoolExecutor(max_workers=2)` — 2 Oracle conns per slot).

Evidence: `rq-semaphore-wiring` — backend-engineer log; stress-soak-report.md §Production Readiness Gate; ADR-0011.

## Async Routing Pre-Check Pattern — COUNT(*) Fail-Open for Domains Without Date Range

**Domains that cannot estimate query cost from a date range use a `count_*_rows()` → `classify_query_cost(domain=..., row_count=count)` call as the L3 estimator.** The COUNT error path MUST fail-open to the sync response (never 503).

Pattern (wip_routes / api_detail):
```python
try:
    row_count = count_wip_rows(...)
    cost = classify_query_cost(domain="wip", row_count=row_count)
    if cost >= QueryCostTier.L3 and is_async_available():
        return enqueue_query_job(...)  # 202
except Exception:
    pass  # fail-open → sync path below
```

The `count_*_rows()` function must reproduce the same filter predicate as the main query so the estimate is tight. For domains with a date range, `classify_query_cost(domain=..., date_span_days=...)` is preferred (no extra DB round-trip).

Evidence: `query-path-c-elimination-cleanup` — spec-architect D2 decision; `wip_service.count_wip_rows`; `test_wip_rowcount_rq_routing.py::test_wip_count_error_fails_open_stays_inline`.

## DW_MES_WIP Has No CONTAINERID Index — Bridge Through DW_MES_CONTAINER

**`DWH.DW_MES_WIP` (95M+ rows) has no index on `CONTAINERID` — only `CONTAINERNAME` and `TXNDATE`** (confirmed via `ALL_TABLES`/`ALL_IND_COLUMNS` against the real dev DB). Any join or dedup keyed on `CONTAINERID` (e.g. `ROW_NUMBER() OVER (PARTITION BY CONTAINERID ...)`, the pattern copied from `mid_section_defect`'s precedent query) forces a full-table scan regardless of how tightly the outer query is date/predicate-scoped — measured: unscoped timeout (55s call_timeout); date-scoped to ~36K containers still 47.5s; further predicate-scoped to ~16.7K containers still 41s. The cost is dominated by the mandatory full scan itself, not join cardinality — narrowing the outer scope does not meaningfully help.

Fix: bridge through `DWH.DW_MES_CONTAINER` (5.5M rows, indexed on **both** `CONTAINERID` and `CONTAINERNAME`) to translate the `CONTAINERID` scope into `CONTAINERNAME`s first, then join `DW_MES_WIP` via its indexed `CONTAINERNAME` column instead. Measured after fix: the same 30-day query dropped from timeout to ~22-32s.

Unverified whether the `mid_section_defect` precedent query (origin of this join pattern) tolerates the full scan because its container set is always small — flag for follow-up if that query is ever touched.

Evidence: `production-achievement-kanban` — `sql/production_achievement.sql`; verified against the real dev Oracle DB with explicit user authorization for each live-connection diagnostic query.
