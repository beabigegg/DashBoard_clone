## 1. LineageEngine Admission Control

- [x] 1.1 Add `LINEAGE_MAX_SEED_COUNT` (default 80000) and `LINEAGE_RSS_REJECT_MB` (default 900) env var constants to `lineage_engine.py`
- [x] 1.2 Add seed count check at entry of `resolve_full_genealogy()`: raise `ValueError` if `len(container_ids) > LINEAGE_MAX_SEED_COUNT`
- [x] 1.3 Add seed count check at entry of `resolve_forward_tree()`: same logic as 1.2
- [x] 1.4 Add RSS guard at entry of both methods: call `process_rss_mb()`, raise `MemoryError` if exceeds `LINEAGE_RSS_REJECT_MB`, skip if None
- [x] 1.5 Add per-batch progress logging in `resolve_split_ancestors()`: log INFO every 5 batches when total batches > 5
- [x] 1.6 Add unit tests: seed count > limit → ValueError; RSS > limit → MemoryError; small inputs → normal execution

## 2. Trace Events MSD CID Limit 豁免移除

- [x] 2.1 Remove the `is_msd` bypass block in `trace_routes.py` (lines 771-775): delete `if is_msd and cid_count > TRACE_EVENTS_CID_LIMIT: (log warning only)` special case
- [x] 2.2 Modify the CID limit check (line 760) to apply to ALL profiles: change `if not is_msd and cid_count > TRACE_EVENTS_CID_LIMIT` to `if cid_count > TRACE_EVENTS_CID_LIMIT`
- [x] 2.3 Before the hard 413 rejection, add async fallback attempt: if `cid_count > TRACE_EVENTS_CID_LIMIT` and `is_async_available()`, enqueue async job and return 202
- [x] 2.4 Update existing unit tests: remove MSD-bypass-specific tests, add test for MSD profile hitting CID limit → 202 (async) or 413 (no async)

## 3. MSD Lineage Async Job Service

- [x] 3.1 Create `msd_lineage_job_service.py` with `enqueue_msd_lineage()`, `get_msd_lineage_job_status()`, `get_msd_lineage_job_result()` using `async_query_job_service` shared utilities
- [x] 3.2 Implement `_execute_msd_lineage_job()` RQ worker entry point: accept job_id, container_ids, direction; call LineageEngine in batches
- [x] 3.3 Implement batched split ancestor resolution: decompose seeds by `ORACLE_IN_BATCH_SIZE`, accumulate `child_to_parent` and `cid_to_name` across batches, update job progress after each batch
- [x] 3.4 Implement merge source resolution after split completion: collect all unique ancestor CIDs, call `resolve_merge_sources()`, build complete ancestors mapping
- [x] 3.5 Implement graph-to-parquet serialization: convert lineage graph to edge-list DataFrame (seed_cid, ancestor_cid, edge_type, cid_name), store via `store_spooled_df()` with namespace `msd-lineage`
- [x] 3.6 Implement result reconstruction: load parquet spool, reconstruct the response dict format expected by `useTraceProgress` (ancestors, cid_to_name, parent_map, nodes, edges)

## 4. Trace Routes Lineage Async Integration

- [x] 4.1 Add `LINEAGE_SEED_ASYNC_THRESHOLD` env var (default 5000) to `trace_routes.py`
- [x] 4.2 In `/lineage` endpoint: add seed count check for MSD profile — if `len(container_ids) > LINEAGE_SEED_ASYNC_THRESHOLD` and `is_async_available()`, call `enqueue_msd_lineage()` and return 202
- [x] 4.3 Add `/lineage/job/<job_id>` GET endpoint for lineage job status polling
- [x] 4.4 Add `/lineage/job/<job_id>/result` GET endpoint for lineage job result retrieval (load from parquet spool, reconstruct response)
- [x] 4.5 Add rate limiter for lineage job endpoints (reuse existing trace rate limit config)

## 5. Frontend useTraceProgress Async Lineage Support

- [x] 5.1 In `useTraceProgress.js` `execute()`: after lineage POST, check if response contains `{async: true, status_url}` — if so, poll via `pollJobUntilComplete()` then fetch result
- [x] 5.2 Update `job_progress` reactive state to reflect lineage stage progress (not just events)
- [x] 5.3 Ensure `collectAllContainerIds()` works correctly with both sync and async lineage response formats

## 6. Testing & Configuration

- [x] 6.1 Add unit tests for `msd_lineage_job_service.py`: mock LineageEngine, verify batching, verify parquet spool, verify progress updates
- [x] 6.2 Add integration test: MSD trace pipeline with seed count > threshold → async lineage → events → aggregation completes (route-level tests in test_trace_routes.py)
- [x] 6.3 Update `.env.example`: add `LINEAGE_SEED_ASYNC_THRESHOLD`, `LINEAGE_MAX_SEED_COUNT`, `LINEAGE_RSS_REJECT_MB` with descriptions
- [x] 6.4 Update `contract/api_inventory.md`: add `/api/trace/lineage/job/<job_id>` and `/api/trace/lineage/job/<job_id>/result` endpoints
