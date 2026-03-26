## 1. EventFetcher Iterator Mode

- [ ] 1.1 Add `fetch_events_iter(container_ids, domain, batch_size)` static method to `EventFetcher` class: yields `Dict[str, List[Dict]]` batches using `read_sql_df_slow_iter`
- [ ] 1.2 Add unit tests for `fetch_events_iter` (mock read_sql_df_slow_iter, verify batch yields)

## 2. NDJSON Stream Endpoint

- [x] 2.1 Add `GET /api/trace/job/<job_id>/stream` endpoint: returns `Content-Type: application/x-ndjson` with Flask `Response(generate(), mimetype='application/x-ndjson')`
- [x] 2.2 Implement NDJSON generator: yield `meta` → `domain_start` → `records` batches → `domain_end` → `aggregation` → `complete` lines
- [x] 2.3 Add `TRACE_STREAM_BATCH_SIZE` env var (default 5000)
- [x] 2.4 Modify `execute_trace_events_job()` to store results in chunked Redis keys: `trace:job:{job_id}:result:{domain}:{chunk_idx}`
- [x] 2.5 Add unit tests for NDJSON stream endpoint

## 3. Result Pagination API

- [x] 3.1 Enhance `GET /api/trace/job/<job_id>/result` with `domain`, `offset`, `limit` query params
- [x] 3.2 Implement pagination over chunked Redis keys
- [x] 3.3 Add unit tests for pagination (offset/limit boundary cases)

## 4. Frontend Streaming Consumer

- [x] 4.1 Add `consumeNDJSONStream(url, onChunk)` utility using `ReadableStream`
- [x] 4.2 Modify `useTraceProgress.js`: for async jobs, prefer stream endpoint over full result endpoint
- [x] 4.3 Add progressive rendering: update table data as each NDJSON batch arrives
- [x] 4.4 Add error handling: stream interruption, malformed NDJSON lines

## 5. Deployment

- [x] 5.1 Update `.env.example`: add `TRACE_STREAM_BATCH_SIZE` with description

## 6. Verification

- [x] 6.1 Run `python -m pytest tests/ -v` — all existing tests pass
- [x] 6.2 Run `cd frontend && npm run build` — frontend builds successfully
- [ ] 6.3 Manual test: verify NDJSON stream produces valid output for multi-domain query
