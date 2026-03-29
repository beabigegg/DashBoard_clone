## ADDED Requirements

### Requirement: Reject History API SHALL implement Type B async polling semantic contract on view miss
The reject-history domain is classified as **Type B** per the `query-response-semantic-contract`. When a view request results in a 410 `cache_expired` response, the complete end-to-end contract is:

1. Client receives HTTP 410 from the view endpoint
2. Client POSTs to the async query endpoint (`/reject/query`) with original query parameters
3. Server enqueues RQ job and returns HTTP 202 with `job_id`
4. Client polls job status until job completes
5. Client requests the view again with the same `query_id` (or new `query_id` from job result)

The `apply_view()` function SHALL NOT auto-dispatch the async job on miss. The view endpoint only handles view computation; primary query dispatch is the client's responsibility.

#### Scenario: View miss triggers Type B async re-query flow
- **WHEN** the client calls the reject view endpoint with a `query_id` whose spool has expired
- **THEN** the server SHALL return HTTP 410 `{ success: false, error: "cache_expired" }`
- **THEN** the client SHALL POST to `/api/reject/query` with original date and filter parameters
- **THEN** the server SHALL enqueue an RQ job and return HTTP 202 with `{ job_id, async: true }`
- **THEN** the client SHALL poll `/api/reject/query/status/<job_id>` until `status == "completed"`
- **THEN** the client SHALL request the view endpoint again using the completed job's `query_id`

#### Scenario: View endpoint does not dispatch on miss
- **WHEN** `apply_view(query_id)` returns `None` in the reject view route
- **THEN** the route SHALL call `cache_expired_error()` and return HTTP 410
- **THEN** the route SHALL NOT call `enqueue_job()` or `execute_primary_query()`
- **THEN** no RQ job SHALL be created as a side-effect of the view request

#### Scenario: Async path unchanged — 202 on fresh query
- **WHEN** the client POSTs a new query to `/api/reject/query` with a long date range and async is available
- **THEN** `should_use_async()` SHALL return `True`
- **THEN** the server SHALL enqueue an RQ job and return HTTP 202 with `job_id`
- **THEN** this behavior SHALL be unchanged by Phase 4
