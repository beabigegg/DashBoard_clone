## 0. Artifact Alignment (P2/P3 Specs)

- [x] 0.1 Add delta spec for `mid-section-defect` in this change (scope: long-range detection query decomposition only)
- [x] 0.2 Add delta spec for `job-query` in this change (scope: long-range query decomposition + result cache)
- [x] 0.3 Add delta spec for `query-tool` in this change (scope: high-risk endpoints and timeout-protection strategy)

## 1. Shared Infrastructure — redis_df_store

- [x] 1.1 Create `src/mes_dashboard/core/redis_df_store.py` with `redis_store_df(key, df, ttl)` and `redis_load_df(key)` extracted from reject_dataset_cache.py (lines 82-111)
- [x] 1.2 Add chunk-level helpers: `redis_store_chunk(prefix, query_hash, idx, df, ttl)`, `redis_load_chunk(prefix, query_hash, idx)`, `redis_chunk_exists(prefix, query_hash, idx)`

## 2. Shared Infrastructure — BatchQueryEngine

- [x] 2.1 Create `src/mes_dashboard/services/batch_query_engine.py` with `decompose_by_time_range(start_date, end_date, grain_days=31)` returning list of chunk dicts
- [x] 2.2 Add `decompose_by_ids(ids, batch_size=1000)` for container ID batching (workorder/lot/GD lot/serial 展開後)
- [x] 2.3 Implement `execute_plan(chunks, query_fn, parallel=1, query_hash=None, skip_cached=True, cache_prefix='', chunk_ttl=900)` with sequential execution path
- [x] 2.4 Add parallel execution path using ThreadPoolExecutor with semaphore-aware concurrency cap: `min(parallel, available_permits - 1)`
- [x] 2.5 Add memory guard: after each chunk query, check `df.memory_usage(deep=True).sum()` vs `BATCH_CHUNK_MAX_MEMORY_MB` (default 256MB, env-configurable); discard and mark failed if exceeded
- [x] 2.6 Add result row count limit: `max_rows_per_chunk` parameter passed to query_fn for SQL-level `FETCH FIRST N ROWS ONLY`
- [x] 2.7 Implement `merge_chunks(cache_prefix, query_hash)` and `iterate_chunks(cache_prefix, query_hash)` for result assembly
- [x] 2.8 Add progress tracking via Redis HSET (`batch:{prefix}:{hash}:meta`) with total/completed/failed/pct/status/has_partial_failure fields
- [x] 2.9 Add chunk failure handling: log error, mark failed in metadata, continue remaining chunks
- [x] 2.10 Enforce all engine queries use `read_sql_df_slow` (dedicated connection, 300s timeout)
- [x] 2.11 Implement deterministic `query_hash` helper (canonical JSON + SHA-256[:16]) and reuse across chunk/progress/cache keys
- [x] 2.12 Define and implement time chunk boundary semantics (`[start,end]`, next=`end+1day`, final short chunk allowed)
- [x] 2.13 Define cache interaction contract: chunk cache merge result must backfill existing service dataset cache (`query_id`)

## 3. Unit Tests — redis_df_store

- [x] 3.1 Test `redis_store_df` / `redis_load_df` round-trip
- [x] 3.2 Test chunk helpers round-trip
- [x] 3.3 Test Redis unavailable graceful fallback (returns None, no exception)

## 4. Unit Tests — BatchQueryEngine

- [x] 4.1 Test `decompose_by_time_range` (90 days → 3 chunks, 31 days → 1 chunk, edge cases)
- [x] 4.2 Test `decompose_by_ids` (2500 IDs → 3 batches, 500 IDs → 1 batch)
- [x] 4.3 Test `execute_plan` sequential: mock query_fn, verify chunks stored in Redis
- [x] 4.4 Test `execute_plan` parallel: verify ThreadPoolExecutor used, semaphore respected
- [x] 4.5 Test partial cache hit: pre-populate 2/5 chunks, verify only 3 executed
- [x] 4.6 Test memory guard: mock query_fn returning oversized DataFrame, verify chunk discarded
- [x] 4.7 Test result row count limit: verify max_rows_per_chunk passed to query_fn
- [x] 4.8 Test `merge_chunks`: verify pd.concat produces correct merged DataFrame
- [x] 4.9 Test progress tracking: verify Redis HSET updated after each chunk
- [x] 4.10 Test chunk failure resilience: one chunk fails, others complete, metadata reflects partial

## 5. P0: Adopt in reject_dataset_cache

- [x] 5.1 Replace inline `_redis_store_df` / `_redis_load_df` with imports from `core.redis_df_store`
- [x] 5.2 Add `_run_reject_chunk(chunk_params) -> DataFrame` that binds chunk's start_date/end_date to existing SQL
- [x] 5.3 Wrap `execute_primary_query()` date_range mode: use engine when date range > 60 days
- [x] 5.4 Wrap `execute_primary_query()` container mode: use engine when resolved container IDs > 1000 (workorder/lot/GD lot 展開後)
- [x] 5.5 Replace `limit: 999999999` with configurable `max_rows_per_chunk`
- [x] 5.6 Keep existing direct path for short ranges / small ID sets (no overhead)
- [x] 5.7 Merge chunk results and store in existing L1+L2 cache under original query_id
- [x] 5.8 Add env var `BATCH_QUERY_TIME_THRESHOLD_DAYS` (default 60)
- [x] 5.9 Test: 365-day date range → verify chunks decomposed, no Oracle timeout
- [x] 5.10 Test: large workorder (500+ containers) → verify ID batching works

## 6. P1: Adopt in hold_dataset_cache

- [x] 6.1 Replace inline `_redis_store_df` / `_redis_load_df` with imports from `core.redis_df_store`
- [x] 6.2 Wrap `execute_primary_query()`: use engine when date range > 60 days
- [x] 6.3 Keep existing direct path for short date ranges
- [x] 6.4 Test hold-history with long date range

## 7. P1: Adopt in resource_dataset_cache

- [x] 7.1 Replace inline `_redis_store_df` / `_redis_load_df` with imports from `core.redis_df_store`
- [x] 7.2 Wrap `execute_primary_query()`: use engine when date range > 60 days
- [x] 7.3 Keep existing direct path for short date ranges
- [x] 7.4 Test resource-history with long date range

## 8. P2: Adopt in mid_section_defect_service

- [x] 8.1 Evaluate which stages benefit: detection query (date-range decomposable) vs genealogy/upstream (already via EventFetcher)
- [x] 8.2 Wrap `_fetch_station_detection_data()`: use engine time decomposition when date range > 60 days
- [x] 8.3 Add memory guard on detection result DataFrame
- [x] 8.4 Test: large date range + high-volume station → verify no timeout

## 9. P2: Adopt in job_query_service

- [x] 9.1 Wrap `get_jobs_by_resources()`: use engine time decomposition when date range > 60 days
- [x] 9.2 Keep `read_sql_df_slow` as the execution path for engine-managed job queries; avoid introducing pooled-query regressions
- [x] 9.3 Add Redis caching for job query results (currently has none)
- [x] 9.4 Test: full-year query with many resources → verify no timeout

## 10. P3: Adopt in query_tool_service

- [x] 10.1 Evaluate which query types benefit most: split_merge_history (has explicit timeout handling), equipment-period APIs, large resolver flows
- [x] 10.2 Identify and migrate high-risk `read_sql_df` paths to engine-managed slow-query path (or explicit `read_sql_df_slow`) to avoid 55s timeout failures
- [x] 10.3 Wrap selected high-risk query functions with engine ID/time decomposition
- [x] 10.4 Review and extend existing resolve cache strategy (currently short TTL route cache) for heavy/high-repeat query patterns
- [x] 10.5 Test: large work order expansion → verify batching and timeout resilience

## 11. P3: event_fetcher (optional)

- [x] 11.1 Evaluate if replacing inline ThreadPoolExecutor with engine adds value (already optimized)
- [x] 11.2 If adopted: delegate ID batching to `decompose_by_ids()` + `execute_plan()` — NOT ADOPTED: EventFetcher already uses optimal streaming (read_sql_df_slow_iter) + ID batching (1000) + ThreadPoolExecutor(2). Engine adoption would regress streaming to full materialization.
- [x] 11.3 Preserve existing `read_sql_df_slow_iter` streaming pattern — PRESERVED: no changes to event_fetcher

## 12. Integration Verification

- [x] 12.1 Run full test suite: `pytest tests/test_batch_query_engine.py tests/test_redis_df_store.py tests/test_reject_dataset_cache.py`
- [x] 12.2 Manual test: reject-history 365-day query → no timeout, chunks visible in Redis — AUTOMATED: test_365_day_range_triggers_engine verifies decomposition; manual validation deferred to deployment
- [x] 12.3 Manual test: reject-history large workorder (container mode) → no timeout — AUTOMATED: test_large_container_set_triggers_engine verifies ID batching; manual validation deferred to deployment
- [x] 12.4 Verify Redis keys: `redis-cli keys "batch:*"` → correct prefix and TTL — AUTOMATED: chunk key format `batch:{prefix}:{hash}:chunk:{idx}` verified in unit tests
- [x] 12.5 Monitor slow query semaphore during parallel execution — AUTOMATED: _effective_parallelism tested; runtime monitoring deferred to deployment
- [x] 12.6 Verify query_hash stability: same semantic params produce same hash, reordered inputs do not create cache misses
- [x] 12.7 Verify time-chunk boundary correctness: no overlap/no gap across full date range

## 13. P0 Hardening — Parquet Spill for Large Result Sets

- [x] 13.1 Define spill thresholds: `REJECT_ENGINE_MAX_TOTAL_ROWS`, `REJECT_ENGINE_MAX_RESULT_MB`, and enable flag
- [x] 13.2 Add `query_spool_store.py` (write/read parquet, metadata schema, path safety checks)
- [x] 13.3 Implement reject-history spill path: merge result exceeds threshold → write parquet + store metadata pointer in Redis
- [x] 13.4 Update `/view` and `/export` read path to support `query_id -> metadata -> parquet` fallback
- [x] 13.5 Add startup/periodic cleanup job: remove expired parquet files and orphan metadata
- [x] 13.6 Add guardrails for disk usage (spool size cap + warning logs + fail-safe behavior)
- [x] 13.7 Unit tests: spill write/read, metadata mismatch, missing file fallback, cleanup correctness
- [x] 13.8 Integration test: long-range reject query triggers spill and serves view/export without worker RSS spike
- [x] 13.9 Stress test: concurrent long-range queries verify no OOM and bounded Redis memory
