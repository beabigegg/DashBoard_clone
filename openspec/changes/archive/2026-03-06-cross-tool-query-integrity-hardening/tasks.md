## 1. Query Quality Contract Foundation

- [x] 1.1 Create shared `QueryQualityMeta` schema/helper module (status/reasons/scope + optional fields)
- [x] 1.2 Add helper functions to merge domain-level quality signals into query-level quality metadata
- [x] 1.3 Add adapter utility for backward-compatible transition from legacy metadata shape
- [x] 1.4 Add unit tests for schema validation and merge behavior (complete/partial/truncated)

## 2. EventFetcher Contract Refactor

- [x] 2.1 Refactor `EventFetcher.fetch_events` return shape to separate `records_by_cid` and `quality_meta`
- [x] 2.2 Remove `__meta__` injection into CID->records map and update internal truncation handling
- [x] 2.3 Ensure truncation metadata includes row-limit context (`observed`, `limit`, `domain`)
- [x] 2.4 Update `tests/test_event_fetcher.py` for new contract and truncation assertions

## 3. Trace Sync/Async/NDJSON Propagation

- [x] 3.1 Update `/api/trace/events` sync path to aggregate and return top-level + per-domain `quality_meta`
- [x] 3.2 Update `trace_job_service` async result persistence to store and return `quality_meta`
- [x] 3.3 Extend NDJSON stream protocol with `quality_meta` event and keep parity with job result
- [x] 3.4 Update `frontend/src/shared-composables/useTraceProgress.js` to consume and preserve `quality_meta`
- [x] 3.5 Add/extend route and job tests for sync/async/stream metadata parity

## 4. MSD Metadata-Safe Aggregation

- [x] 4.1 Refactor MSD normalizers to process record collections only and ignore metadata side-channel fields
- [x] 4.2 Update staged aggregation entrypoints to accept explicit quality metadata input
- [x] 4.3 Surface MSD response-level `quality_meta` for non-complete upstream/downstream events
- [x] 4.4 Add regression tests covering truncated/partial EventFetcher payloads in MSD pipeline

## 5. Query Tool High-Volume Pagination

- [x] 5.1 Add `page/per_page` contract for lot-history batch and high-volume association/equipment-lots endpoints
- [x] 5.2 Implement server-side pagination in service layer with bounded `per_page` and pagination metadata
- [x] 5.3 Include `quality_meta` in paginated detail responses where EventFetcher is involved
- [x] 5.4 Update query-tool frontend composables/components to request and render paginated data
- [x] 5.5 Add backend/frontend tests for pagination behavior and metadata visibility

## 6. Material Trace Streaming Export + Metadata

- [x] 6.1 Replace export full-buffer generation with streaming CSV generator in material-trace service/route
- [x] 6.2 Keep existing CSV contract (BOM, header order, filename) while streaming
- [x] 6.3 Normalize query/export completeness reporting to `quality_meta` + machine-readable headers
- [x] 6.4 Add tests for streaming export, truncation signaling, and no-regression CSV format

## 7. Cross-Tool Partial-Failure Reuse

- [x] 7.1 Extract reusable helper pattern from reject-history partial-failure semantics (`failed_chunk_count`, `failed_ranges`)
- [x] 7.2 Apply shared helper in relevant non-reject high-volume query paths
- [x] 7.3 Ensure partial-failure metadata survives cache-hit restore flows where applicable
- [x] 7.4 Add unit tests for helper reuse and cross-tool metadata consistency

## 8. Config, Docs, and Rollout Safety

- [x] 8.1 Add missing env docs in `.env.example` for completeness/guard settings (`EVENT_FETCHER_MAX_TOTAL_ROWS`, `QUERY_TOOL_RSS_REJECT_MB`, `TRACE_SYNC_RSS_REJECT_MB`, `MATERIAL_TRACE_MAX_RESULT_MB`)
- [x] 8.2 Update operational docs to describe quality meta semantics and non-complete-result handling
- [x] 8.3 Add rollout checklist (compat adapter toggle, smoke checks, rollback path)
- [x] 8.4 Run targeted test suites and capture verification evidence in change notes
