## 0. Pre-work: DuckDB Coverage Audit

- [ ] 0.1 Audit `resource_history_sql_runtime.py`: verify it produces equivalent output to `_derive_kpi()`, `_derive_trend()`, `_derive_heatmap()`, `_derive_comparison()`, `_derive_detail()` for all valid param combinations
- [ ] 0.2 Audit `hold_history_sql_runtime.py`: verify coverage for `_derive_trend()` (incl. 07:30 shift boundary), `_derive_reason_pareto()`, `_derive_duration()`, `_derive_list()`
- [ ] 0.3 Audit `yield_alert_sql_runtime.py`: verify coverage for all view types including station_summary, package_summary, alerts pagination
- [ ] 0.4 Audit `reject_cache_sql_runtime.py`: verify coverage for analytics, summary, detail, pareto (all param combinations including pareto_dimension, pareto_values, pareto_selections)
- [ ] 0.5 For any coverage gap found: add missing SQL in the runtime module before removing the pandas fallback

## 1. resource_dataset_cache.py — retire pandas fallback

- [ ] 1.1 In `apply_view()` (L330): locate the `# ── Pandas fallback path ──` block (L358–379) and remove it; replace with `return None` (→ route returns 410 cache_expired) when `sql_result is None`
- [ ] 1.2 Delete `_derive_summary()` (L380), `_derive_kpi()` (L476), `_derive_trend()` (L513), `_derive_heatmap()` (L563), `_derive_comparison()` (L633), `_derive_detail()` (L697) and all sub-helpers
- [ ] 1.3 Check if `_get_cached_df()` (L92) is still reachable after 1.1 — if only called from view fallback (now removed), remove it; if still called by engine-path warmup at L289, keep it
- [ ] 1.4 Remove `import pandas as pd` if no longer needed after dead code removal

## 2. hold_dataset_cache.py — retire pandas fallback

- [ ] 2.1 In `apply_view()` (L293): locate the `# ── Pandas fallback path ──` block (L348–368) and remove it; return `None` when `sql_result is None`
- [ ] 2.2 Delete `_derive_all_views()` (L369), `_derive_trend()` (L500), `_derive_reason_pareto()` (L574), `_derive_duration()` (L612), `_derive_list()` (L646) and sub-helpers
- [ ] 2.3 Check if `_get_cached_df()` (L134) is still reachable — remove if dead, keep if used by warmup at L248
- [ ] 2.4 Remove `import pandas as pd` if no longer needed

## 3. yield_alert_dataset_cache.py — retire pandas fallback

- [ ] 3.1 In `apply_view()` (L1416): locate the `# ── Task 5.3: Pandas fallback path ──` block (L1497–~1623) and remove it; return `None` when DuckDB path produces no result
- [ ] 3.2 Check `_load_detail_df_from_spool()` (L621): if only called from the pandas fallback block, delete it
- [ ] 3.3 Check if `enforce_dataset_memory_guard` guard (L770 comment) is still needed — it was on the pandas fallback path only; remove if dead
- [ ] 3.4 Remove `import pandas as pd` if no longer needed

## 4. reject_dataset_cache.py — retire pandas fallback

- [ ] 4.1 In `apply_view()` (L1291): locate the legacy fallback block starting at L1345 (`_allow_legacy_fallback` check) through the pandas derive section (~L1358–end of function)
- [ ] 4.2 Remove the `_allow_legacy_fallback()` gate and the legacy pandas path; when `sql_result is None`, return `None` directly (route returns 410)
- [ ] 4.3 Delete `_allow_legacy_fallback()` function (L171) if no longer called anywhere
- [ ] 4.4 Delete `_REJECT_CACHE_SQL_VIEW_FALLBACK_LEGACY_ENABLED` flag if no longer used
- [ ] 4.5 Delete `_derive_analytics_raw()` (L1528), `_derive_summary_from_analytics()` (L1571), `_derive_trend_from_analytics()` (L1594) if only called from the legacy view path
- [ ] 4.6 Keep async RQ path, `execute_primary_query()`, and the 202 response path unchanged

## 5. 測試更新

- [ ] 5.1 `test_resource_dataset_cache.py`: remove tests that mock `_derive_*` pandas functions; add test: `sql_result=None` → `apply_view()` returns `None`
- [ ] 5.2 `test_hold_dataset_cache.py`: same pattern — remove `_derive_*` mocks; add test: DuckDB returns None → `apply_view()` returns None
- [ ] 5.3 `test_yield_alert_dataset_cache.py` (if exists): remove pandas fallback path tests; add test: DuckDB failure → None
- [ ] 5.4 `test_reject_dataset_cache.py`: remove legacy fallback tests; add test: sql_result=None → apply_view returns None

## 6. Governed Spec Updates

- [ ] 6.1 Confirm `openspec/specs/parquet-spool-view-engine/spec.md` is updated (this change's delta spec covers it)
- [ ] 6.2 Confirm `openspec/specs/resource-dataset-cache/spec.md` reflects removed derive requirements
- [ ] 6.3 Confirm `openspec/specs/hold-dataset-cache/spec.md` reflects removed derive requirements
- [ ] 6.4 Confirm `openspec/specs/yield-alert-spool-query/spec.md` reflects pandas fallback removed
- [ ] 6.5 Confirm `openspec/specs/reject-history-api/spec.md` reflects DuckDB-sole-engine requirement

## 7. Validation

- [ ] 7.1 `pytest tests/ -v` — all tests pass (allow 2 pre-existing `TestWarmupTasks` failures)
- [ ] 7.2 Smoke test resource-history: `PHASE2_METADATA_ONLY=1` — POST execute, GET view → returns DuckDB result with no `fallback_reason` in pandas path
- [ ] 7.3 Smoke test hold-history: same pattern
- [ ] 7.4 Smoke test yield-alert: verify alerts computed fully in DuckDB, no pandas fallback log
- [ ] 7.5 Smoke test reject-history: POST execute (async), GET view after completion → DuckDB result
- [ ] 7.6 Confirm gunicorn RSS drops (compare with Phase 2 baseline via `/admin/api/performance-detail`)
