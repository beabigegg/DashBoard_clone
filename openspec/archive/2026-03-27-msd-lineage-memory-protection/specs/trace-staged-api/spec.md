## MODIFIED Requirements

### Requirement: Staged trace API SHALL expose events endpoint
`POST /api/trace/events` SHALL query events for specified domains using `EventFetcher`.

#### Scenario: Normal events query
- **WHEN** request body contains `{ "profile": "query_tool", "container_ids": [...], "domains": ["history", "materials"] }`
- **THEN** the endpoint SHALL return `{ "stage": "events", "results": { "history": { "data": [...], "count": N }, "materials": { "data": [...], "count": N } }, "aggregation": null }`

#### Scenario: mid_section_defect profile with aggregation
- **WHEN** request body contains `{ "profile": "mid_section_defect", "container_ids": [...], "domains": ["upstream_history"] }`
- **THEN** the endpoint SHALL automatically run aggregation logic after event fetching

#### Scenario: Async enqueue uses shared async_query_job_service
- **WHEN** `cid_count > TRACE_ASYNC_CID_THRESHOLD` and async is available
- **THEN** `trace_job_service.py` SHALL delegate enqueue and status operations to `async_query_job_service` shared utilities
- **THEN** the trace-specific worker entry point `execute_trace_events_job()` and NDJSON streaming SHALL remain in `trace_job_service.py`

#### Scenario: MSD profile CID limit enforcement
- **WHEN** request body contains `profile=mid_section_defect` and `len(container_ids) > TRACE_EVENTS_CID_LIMIT`
- **THEN** the endpoint SHALL attempt async fallback (same as non-MSD profiles)
- **THEN** if async is available, the endpoint SHALL return HTTP 202 with job handles
- **THEN** if async is unavailable, the endpoint SHALL return HTTP 413 with `CID_LIMIT_EXCEEDED`
- **THEN** the endpoint SHALL NOT bypass the CID limit for MSD profile

#### Scenario: Admission control is profile-agnostic
- **WHEN** any profile request exceeds `TRACE_EVENTS_CID_LIMIT`
- **THEN** the same admission control logic SHALL apply regardless of profile
- **THEN** there SHALL be no profile-specific CID limit exemptions
