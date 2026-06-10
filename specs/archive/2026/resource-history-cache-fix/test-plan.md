---
change-id: resource-history-cache-fix
schema-version: 0.1.0
last-changed: 2026-06-10
risk: high
tier: 1
---

# Test Plan: resource-history-cache-fix

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | test name | tier |
|---|---|---|---|---|
| AC-1 | unit | tests/test_resource_dataset_cache.py | `TestCanonicalSpoolHit::test_ensure_dataset_loaded_produces_canonical_hit` | Tier 0 |
| AC-1 | integration | tests/e2e/test_resource_history_e2e.py | extend `TestResourceHistorySpoolReuse::test_canonical_spool_hit_skips_oracle` | Tier 1 |
| AC-2 | unit | tests/test_resource_dataset_cache.py | `TestCanonicalKeyParity::test_ensure_dataset_loaded_writes_canonical_key` | Tier 0 |
| AC-2 | unit | tests/test_resource_dataset_cache.py | `TestCanonicalKeyParity::test_execute_primary_query_empty_filter_co_writes_canonical_key` | Tier 0 |
| AC-2 | unit | tests/test_resource_dataset_cache.py | `TestCanonicalKeyParity::test_empty_filter_detection_non_empty_does_not_co_write` | Tier 0 |
| AC-3 | unit | tests/test_resource_history_sql_runtime.py | `TestCanonicalKeyGranularity::test_canonical_key_excludes_granularity` | Tier 0 |
| AC-3 | unit | tests/test_resource_history_sql_runtime.py | `TestCanonicalKeyGranularity::test_day_week_month_year_produce_identical_canonical_key` | Tier 0 |
| AC-3 | integration | tests/e2e/test_resource_history_e2e.py | `TestResourceHistorySpoolReuse::test_granularity_switch_no_new_oracle_call` | Tier 1 |
| AC-4 | unit | tests/test_resource_dataset_cache.py | `TestWarmCacheFilterSwitch::test_filter_switch_on_warm_cache_no_oracle_call` | Tier 0 |
| AC-4 | integration | tests/e2e/test_resource_history_e2e.py | `TestResourceHistorySpoolReuse::test_filter_switch_warm_cache_resolves_from_spool` | Tier 1 |
| AC-5 | contract | tests/test_resource_history_routes.py | extend `TestResourceHistoryQueryAPI::test_successful_query` — assert response keys unchanged | Tier 1 |
| AC-6 | unit | tests/test_resource_cache_version_check.py | `TestRefreshCacheForceTrue::test_refresh_cache_always_fetches_when_version_differs` (existing — must still pass) | Tier 0 |
| AC-6 | resilience | tests/test_resource_dataset_cache.py | `TestSchemaVersionInvalidation::test_schema_version_bump_invalidates_stale_spool` | Tier 0 |
| AC-6 | resilience | tests/test_resource_dataset_cache.py | `TestRedisDownFallback::test_redis_down_falls_back_to_oracle_no_binder_exception` | Tier 0 |
| AC-6 | resilience | tests/test_resource_dataset_cache.py | `TestStaleParquetFallback::test_stale_parquet_schema_mismatch_falls_back_to_oracle` | Tier 0 |
| AC-7 | unit | tests/test_resource_dataset_cache.py | `TestViewResultCache::test_apply_view_result_cached_within_ttl` | Tier 0 |
| AC-7 | unit | tests/test_resource_dataset_cache.py | `TestViewResultCache::test_apply_view_result_recomputed_after_ttl_expiry` | Tier 0 |
| AC-7 | unit | tests/test_resource_dataset_cache.py | `TestViewResultCache::test_resource_view_cache_ttl_zero_disables_cache` | Tier 0 |
| AC-7 | unit | tests/test_resource_dataset_cache.py | `TestViewResultCache::test_apply_view_caches_all_six_structures_atomically` | Tier 0 |
| AC-7 + env | contract | tests/test_env_contract.py | `TestResourceViewCacheTTLDefault::test_resource_view_cache_ttl_default_equals_300` | Tier 0 |
| AC-8 | unit | tests/test_resource_dataset_cache.py | `TestOracleFallbackPath::test_oracle_fallback_used_when_canonical_miss` | Tier 0 |
| AC-8 | e2e | tests/e2e/test_resource_history_e2e.py | `TestResourceHistoryAPIWorkflow` full suite (existing — must pass) | Tier 1 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | Tier 0 | canonical-key builders, warmup write, view-result TTL, resilience fallbacks — `test_resource_dataset_cache.py` + `test_resource_history_sql_runtime.py` |
| contract | Tier 1 | API response shape (extend `test_resource_history_routes.py`); env-default pin for `RESOURCE_VIEW_CACHE_TTL` in `test_env_contract.py` |
| integration | Tier 1 | warmup→query full path; granularity-switch no-Oracle; filter-switch warm cache — extend `TestResourceHistorySpoolReuse` in `tests/e2e/test_resource_history_e2e.py` |
| resilience | Tier 0 | schema_version bump invalidation; Redis-down; stale-parquet schema-mismatch — mock at Redis/spool-store boundary only |

## Tests That Must Fail Before Implementation

- `TestCanonicalKeyParity::test_ensure_dataset_loaded_writes_canonical_key` — warmup currently never writes canonical key
- `TestCanonicalSpoolHit::test_ensure_dataset_loaded_produces_canonical_hit` — currently always SPOOL_MISS
- `TestCanonicalKeyGranularity::test_day_week_month_year_produce_identical_canonical_key` — granularity currently included in key
- `TestViewResultCache::test_apply_view_result_cached_within_ttl` — Phase-2 cache not yet implemented
- `TestResourceViewCacheTTLDefault::test_resource_view_cache_ttl_default_equals_300` — constant not yet defined

## Out of Scope

- Playwright browser E2E (no UI change)
- Multi-worker startup lock (D6 — independent substrate, no code change)
- System-A filter-inclusive key deprecation (deferred to follow-up change)
- Stress / soak tests (not pre-merge per project governance)
- Other feature pages (change bounded to resource-history read path)

## Notes

- Mock at Redis/spool-store boundary (`store_spooled_df`, `register_spool_file`, `redis_df_store.get/set`), not at internal class methods.
- Per CLAUDE.md: use `mock.assert_called_once()` + `call_args.kwargs[key]` for Oracle-call assertions; never `assert_called_once_with()` as a kwarg whitelist.
- `test_env_contract.py` must import the module-level `RESOURCE_VIEW_CACHE_TTL` constant directly; `monkeypatch.setenv` is ineffective for constants frozen at import time.
- Route error-swallow removal (D3) is covered by extending `TestResourceHistoryQueryAPI::test_query_bootstrap_render_failure_returns_500` to verify the exception now propagates.
