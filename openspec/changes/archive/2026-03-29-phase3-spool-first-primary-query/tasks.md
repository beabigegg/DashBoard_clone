## 0. Pre-work: DuckDB Coverage Audit

- [x] 0.1 Audit `resource_history_sql_runtime.py`: verify it produces equivalent output to `_derive_kpi()`, `_derive_trend()`, `_derive_heatmap()`, `_derive_comparison()`, `_derive_detail()` for all valid param combinations
- [x] 0.2 Audit `hold_history_sql_runtime.py`: verify coverage for `_derive_trend()` (incl. 07:30 shift boundary), `_derive_reason_pareto()`, `_derive_duration()`, `_derive_list()`
- [x] 0.3 Audit `yield_alert_sql_runtime.py`: verify coverage for all view types including station_summary, package_summary, alerts pagination
- [x] 0.4 Audit `reject_cache_sql_runtime.py`: verify coverage for analytics, summary, detail, pareto (all param combinations including pareto_dimension, pareto_values, pareto_selections)
- [x] 0.5 For any coverage gap found: add missing SQL in the runtime module before removing the pandas fallback

## 1. resource_dataset_cache.py — retire pandas fallback

- [x] 1.1 In `apply_view()` (L330): locate the `# ── Pandas fallback path ──` block (L358–379) and remove it; replace with `return None` (→ route returns 410 cache_expired) when `sql_result is None`
- [x] 1.2 Delete `_derive_summary()` (L380), `_derive_kpi()` (L476), `_derive_trend()` (L513), `_derive_heatmap()` (L563), `_derive_comparison()` (L633), `_derive_detail()` (L697) and all sub-helpers
  <!-- SCOPE NARROWED: These functions are retained — still called by execute_primary_query() for cold-start (Oracle) path. Deletion from execute_primary_query path is deferred (out of scope for Phase 3). Spec updated via phase3-spool-first-primary-query delta to document this. -->
- [x] 1.3 Check if `_get_cached_df()` (L92) is still reachable after 1.1 — keep: called by execute_primary_query at L213 and engine warmup at L289
- [x] 1.4 Remove `import pandas as pd` if no longer needed — keep: pandas still used by execute_primary_query

## 2. hold_dataset_cache.py — retire pandas fallback

- [x] 2.1 In `apply_view()` (L293): locate the `# ── Pandas fallback path ──` block (L348–368) and remove it; return `None` when `sql_result is None`
- [x] 2.2 Delete `_derive_all_views()` (L369), `_derive_trend()` (L500), `_derive_reason_pareto()` (L574), `_derive_duration()` (L612), `_derive_list()` (L646) and sub-helpers
  <!-- SCOPE NARROWED: These functions are retained — still called by execute_primary_query() at L274 for cold-start (Oracle) path. Deletion deferred, out of scope for Phase 3. Spec updated. -->
- [x] 2.3 Check if `_get_cached_df()` (L134) is still reachable — keep: called by execute_primary_query at L187
- [x] 2.4 Remove `import pandas as pd` if no longer needed — keep: pandas still used by execute_primary_query

## 3. yield_alert_dataset_cache.py — retire pandas fallback

- [x] 3.1 In `apply_view()` (L1416): locate the `# ── Task 5.3: Pandas fallback path ──` block (L1497–~1623) and remove it; return `None` when DuckDB path produces no result
- [x] 3.2 Check `_load_detail_df_from_spool()` (L621): if only called from the pandas fallback block, delete it — deleted (only caller was fallback block)
- [x] 3.3 Check if `enforce_dataset_memory_guard` guard (L770 comment) is still needed — removed from import (only used in fallback block); `maybe_gc_collect` kept (used at L740, L798, L942)
- [x] 3.4 Remove `import pandas as pd` if no longer needed — keep: pandas used extensively in execute_primary_query and other helpers

## 4. reject_dataset_cache.py — retire pandas fallback

- [x] 4.1 In `apply_view()` (L1291): locate the legacy fallback block starting at L1345 (`_allow_legacy_fallback` check) through the pandas derive section (~L1358–end of function)
- [x] 4.2 Remove the `_allow_legacy_fallback()` gate and the legacy pandas path; when `sql_result is None`, return `None` directly (route returns 410)
- [x] 4.3 Delete `_allow_legacy_fallback()` function (L171) if no longer called anywhere — keep: still called at L2100 (batch pareto) and L2257 (export)
- [x] 4.4 Delete `_REJECT_CACHE_SQL_VIEW_FALLBACK_LEGACY_ENABLED` flag if no longer used — deleted (was only used in view path, now removed)
- [x] 4.5 Delete `_derive_analytics_raw()` (L1528), `_derive_summary_from_analytics()` (L1571), `_derive_trend_from_analytics()` (L1594) if only called from the legacy view path — keep: also called from _build_primary_response (L1266) and execute_primary_query response path (L896)
- [x] 4.6 Keep async RQ path, `execute_primary_query()`, and the 202 response path unchanged

## 5. 測試更新

- [x] 5.1 `test_resource_dataset_cache.py`: remove tests that mock `_derive_*` pandas functions; add test: `sql_result=None` → `apply_view()` returns `None`
- [x] 5.2 `test_hold_dataset_cache.py`: same pattern — remove `_derive_*` mocks; add test: DuckDB returns None → `apply_view()` returns None
- [x] 5.3 `test_yield_alert_dataset_cache.py` (if exists): remove pandas fallback path tests; add test: DuckDB failure → None
- [x] 5.4 `test_reject_dataset_cache.py`: remove legacy fallback tests; add test: sql_result=None → apply_view returns None

## 6. Governed Spec Updates

- [x] 6.1 Confirm `openspec/specs/parquet-spool-view-engine/spec.md` is updated (this change's delta spec covers it) — spec dir does not exist; change design.md is authoritative
- [x] 6.2 Confirm `openspec/specs/resource-dataset-cache/spec.md` reflects removed derive requirements — spec dir does not exist; change design.md is authoritative
- [x] 6.3 Confirm `openspec/specs/hold-dataset-cache/spec.md` reflects removed derive requirements — spec dir does not exist; change design.md is authoritative
- [x] 6.4 Confirm `openspec/specs/yield-alert-spool-query/spec.md` reflects pandas fallback removed — updated: spool miss returns None, empty-result marker semantics updated
- [x] 6.5 Confirm `openspec/specs/reject-history-api/spec.md` reflects DuckDB-sole-engine requirement — added Phase 3 delta: DuckDB sole engine, flag removed

## 7. Validation

- [x] 7.1 `pytest tests/ -v` — all tests pass (allow 2 pre-existing `TestWarmupTasks` failures)
- [x] 7.2 Smoke test resource-history: GET view → `view computed via DuckDB (latency_s=0.053)`, no `fallback_reason` in `_meta`
- [x] 7.3 Smoke test hold-history: GET view → `view computed via DuckDB (latency_s=0.028)`, no `fallback_reason` in `_meta`
- [x] 7.4 Smoke test yield-alert: GET view → `view computed via DuckDB (latency_s=0.930)`, `fallback=None` in server log
- [x] 7.5 Smoke test reject-history: GET view → `Reject view served by cache-sql (runtime=duckdb, source=spool)`
- [x] 7.6 Worker RSS: pid=4632 585MB, pid=4634 491MB — well within 3181MB limit; no eviction triggered
