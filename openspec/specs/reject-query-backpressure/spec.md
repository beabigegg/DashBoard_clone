## ADDED Requirements

### Requirement: POST /api/reject-history/query SHALL support async 202 response
The reject-history query endpoint SHALL return HTTP 202 with a job_id when the query qualifies for async execution, allowing the Gunicorn thread to be released immediately. The response SHALL use `success_response()` with `status_code=202`.

#### Scenario: Async path triggered for long date range
- **WHEN** `mode=date_range` and `end_date - start_date > REJECT_ASYNC_DAY_THRESHOLD` (default 10) and `is_async_available()` returns `True`
- **THEN** the endpoint SHALL check cache first (L1/L2/spool)
- **THEN** if cache miss, the endpoint SHALL enqueue the query to the `reject-query` RQ queue
- **THEN** the endpoint SHALL return `success_response({"async": True, "job_id": "<id>", "status_url": "/api/reject-history/job/<id>", "query_id": "<pre-computed>"}, status_code=202)`

#### Scenario: Cache hit bypasses async
- **WHEN** a query qualifies for async but the cache already contains the result (same query_id)
- **THEN** the endpoint SHALL return the cached result via `success_response()` with HTTP 200
- **THEN** no RQ job SHALL be enqueued

#### Scenario: Async unavailable fallback
- **WHEN** a query qualifies for async but `is_async_available()` returns `False`
- **THEN** the endpoint SHALL fall through to the existing synchronous execution path
- **THEN** the endpoint SHALL return HTTP 200 via `success_response()` (same as current behavior)

#### Scenario: Short query remains synchronous
- **WHEN** `mode=date_range` and `end_date - start_date <= 10`
- **THEN** the endpoint SHALL execute synchronously and return HTTP 200 (no change)

#### Scenario: Container mode remains synchronous
- **WHEN** `mode=container`
- **THEN** the endpoint SHALL execute synchronously and return HTTP 200 (no change)

### Requirement: GET /api/reject-history/job/<job_id> SHALL return job status
A new endpoint SHALL allow the frontend to poll the status of an async query job. The endpoint SHALL use the standard response envelope via `success_response()` and `error_response()` helpers. The endpoint SHALL apply `@configured_rate_limit`.

#### Scenario: Rate limiting on job status endpoint
- **WHEN** the endpoint is instantiated
- **THEN** it SHALL use `@configured_rate_limit` with configurable max_requests (default 60) and window_seconds (default 60)

#### Scenario: Job running
- **WHEN** `GET /api/reject-history/job/reject-abc123` is called and the job is executing
- **THEN** the endpoint SHALL return `success_response({"job_id": "reject-abc123", "status": "running", "progress": "3/10", "pct": 30, "elapsed_seconds": 45})`

#### Scenario: Job completed
- **WHEN** the job has finished successfully
- **THEN** the endpoint SHALL return `success_response({"job_id": "reject-abc123", "status": "completed", "query_id": "<id>", "elapsed_seconds": 120})`

#### Scenario: Job failed
- **WHEN** the job has failed
- **THEN** the endpoint SHALL return `success_response({"job_id": "reject-abc123", "status": "failed", "error": "<message>", "elapsed_seconds": 90})`

#### Scenario: Job not found
- **WHEN** `GET /api/reject-history/job/nonexistent` is called
- **THEN** the endpoint SHALL return `not_found_error("Job not found")`

### Requirement: Route handler SHALL pre-check cache before concurrency rejection
The `api_reject_history_query()` route handler SHALL check the cache for the computed query_id before evaluating concurrency limits, ensuring retries after 503 can reuse completed results. Error responses SHALL use `error_response()` helper with appropriate error codes.

#### Scenario: Cache hit before concurrency check
- **WHEN** `get_slow_query_active_count() >= HEAVY_QUERY_REJECT_THRESHOLD` but the cache contains a result for the query_id
- **THEN** the endpoint SHALL return the cached result via `success_response()` with HTTP 200
- **THEN** the endpoint SHALL NOT return 503

#### Scenario: Cache miss with concurrency exceeded
- **WHEN** cache miss and `get_slow_query_active_count() >= HEAVY_QUERY_REJECT_THRESHOLD` (default 4)
- **THEN** the endpoint SHALL return `error_response(SERVICE_UNAVAILABLE, "系統忙碌中，請稍後再試", status_code=503, meta={"retry_after_seconds": 30, "query_id": "<id>"}, headers={"Retry-After": "30"})`

#### Scenario: Cache miss with system memory pressure
- **WHEN** cache miss and `system_memory_pressure` flag is `True` (from worker_memory_guard)
- **THEN** the endpoint SHALL return `error_response(SERVICE_UNAVAILABLE, "系統記憶體不足，請稍後再試", status_code=503, meta={"retry_after_seconds": 30}, headers={"Retry-After": "30"})`

### Requirement: Route handler SHALL keep business logic in service layer
All async job decision logic (`should_use_async`, `enqueue_reject_query`), cache checking, and concurrency evaluation SHALL reside in the service layer (`reject_query_job_service.py` / `reject_dataset_cache.py`). The route handler SHALL only handle HTTP parsing, call services, and format responses using response helpers.

#### Scenario: Route handler is thin
- **WHEN** `api_reject_history_query()` handles an async-eligible request
- **THEN** the route handler SHALL call service functions and use `success_response()` / `error_response()` to format the HTTP response
- **THEN** no business logic (cache checking, async decision, enqueue) SHALL exist directly in the route handler

## MODIFIED Requirements

### Requirement: Reject primary query SHALL check RSS before execution
The `execute_primary_query()` function SHALL reject requests when worker RSS memory exceeds a configurable threshold, preventing the query from inflating memory further.

#### Scenario: RSS below threshold
- **WHEN** `process_rss_mb()` returns a value below `REJECT_QUERY_RSS_REJECT_MB` (default 900)
- **THEN** the query SHALL proceed normally

#### Scenario: RSS above threshold
- **WHEN** `process_rss_mb()` returns a value at or above `REJECT_QUERY_RSS_REJECT_MB`
- **THEN** `execute_primary_query()` SHALL raise `RejectPrimaryQueryOverloadError` with code `SERVICE_UNAVAILABLE`
- **THEN** the error SHALL include `retry_after=30`
- **THEN** the route handler SHALL return `error_response(SERVICE_UNAVAILABLE, ..., status_code=503, headers={"Retry-After": "30"})`

#### Scenario: RSS check occurs before query lock acquisition
- **WHEN** the RSS check triggers rejection
- **THEN** no query lock SHALL have been acquired
- **THEN** no Oracle query SHALL have been executed

#### Scenario: RSS threshold lower than trace/query-tool thresholds
- **WHEN** the default thresholds are used
- **THEN** `REJECT_QUERY_RSS_REJECT_MB` (900) SHALL be lower than `TRACE_SYNC_RSS_REJECT_MB` (1100) and `QUERY_TOOL_RSS_REJECT_MB` (1100)

#### Scenario: psutil unavailable
- **WHEN** `process_rss_mb()` returns `None`
- **THEN** the query SHALL proceed normally (fail-open)

#### Scenario: RSS check skipped in RQ worker
- **WHEN** the query is executed in an RQ worker process (not Gunicorn)
- **THEN** the per-worker RSS check SHALL still apply using the RQ worker's own RSS

### Requirement: Reject query SHALL use unified spool pipeline without RSS guard
Reject query's async path SHALL be integrated into the unified spool pipeline. The independent RSS guard (`REJECT_QUERY_RSS_REJECT_MB`) SHALL be removed as the spool architecture prevents in-memory accumulation.

#### Scenario: Reject query routes to unified pipeline
- **WHEN** a reject-history query is initiated
- **THEN** if a valid spool exists, results SHALL be served from DuckDB
- **THEN** if no spool exists, the query SHALL be enqueued as an RQ job
- **THEN** the query SHALL NOT check `REJECT_QUERY_RSS_REJECT_MB` before execution

#### Scenario: Reject warmup via spool scheduler
- **WHEN** the spool warmup scheduler runs
- **THEN** reject_dataset SHALL be pre-loaded for 90 days (upgraded from 30 days)
- **THEN** reject queries within the 90-day range SHALL be served from DuckDB without RQ job
