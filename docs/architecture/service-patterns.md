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

## RQ Worker Concurrency Gate — acquire_heavy_query_slot Wiring Requirement

**Every `execute_*_job` worker function that runs Oracle-heavy queries MUST wire `acquire_heavy_query_slot` before the owning feature flag is promoted to production.**

The `global_concurrency` semaphore (`MAX_CONCURRENT = 3`) bounds simultaneous Oracle connections from RQ workers to prevent DB exhaustion. Without wiring, flag-on workers bypass the gate entirely — the semaphore exists but is never acquired.

Current gap (as of query-path-c-elimination-cleanup): `execute_query_tool_job`, `execute_hold_query_job`, `execute_resource_query_job`, and `execute_reject_query_job` are all unwired. Wiring pattern:

```python
with acquire_heavy_query_slot():
    result = <oracle call>
```

Pre-production checklist before flipping any `*_USE_RQ=on`:
1. Wire `acquire_heavy_query_slot` in the owning `execute_*_job`.
2. Run real-Oracle load test to confirm `peak_concurrent ≤ MAX_CONCURRENT`.
3. Update stress-soak-report.md with real evidence (mock structural proof alone is insufficient).

Evidence: `query-path-c-elimination-cleanup` — stress-soak-engineer log; stress-soak-report.md §Production Readiness Gate; ADR-0011.

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
