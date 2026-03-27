## Purpose
Define the staged trace API contracts for event querying, async fallback, completeness metadata, and admission control across all trace profiles.

## Requirements

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

### Requirement: Trace events responses SHALL include explicit domain and query completeness metadata
`POST /api/trace/events` responses SHALL carry completeness metadata for each requested domain and for the merged query result.

#### Scenario: Domain-level completeness fields always present
- **WHEN** events endpoint returns domain results for requested domains
- **THEN** each domain result SHALL include `quality_meta` with a valid status (`complete`, `partial`, `truncated`, or `failed`)
- **THEN** top-level response SHALL include merged `quality_meta` and `domain_quality_meta`

#### Scenario: Failed domain represented explicitly
- **WHEN** one requested domain fails during events fetch
- **THEN** response SHALL include that domain with `quality_meta.status = "failed"` and an empty data array for that domain
- **THEN** top-level completeness status SHALL remain non-complete and diagnostics SHALL identify failed scope

### Requirement: Trace events metadata SHALL remain normalized across fresh and cached responses
Completeness metadata shape SHALL be normalized identically for fresh execution and cache-hit replay.

#### Scenario: Cached response normalization
- **WHEN** events endpoint returns a cached events payload
- **THEN** response normalization SHALL ensure `quality_meta` and `domain_quality_meta` are present and schema-consistent with fresh execution responses

### Requirement: Trace events sync path SHALL prefer async fallback under memory pressure
When sync execution is blocked by memory-pressure guard, the endpoint SHALL prefer async job delegation when async execution is available for the request.

#### Scenario: Memory-pressure guard with async available
- **WHEN** sync `POST /api/trace/events` request hits RSS guard and async queue is available
- **THEN** endpoint SHALL return `202` with job handles instead of immediate `503`
- **THEN** response SHALL include status/stream endpoints for polling

#### Scenario: Memory-pressure guard with async unavailable
- **WHEN** sync request hits RSS guard and async queue is unavailable
- **THEN** endpoint SHALL return HTTP `503 SERVICE_UNAVAILABLE`
- **THEN** response SHALL include `Retry-After` header and retryable overload code

### Requirement: Staged trace API SHALL prefer the spool-safe async path for heavy events work
`POST /api/trace/events` SHALL prefer RQ + spool execution for heavy work, while preserving compatibility for cache hits and migrated consumers.

#### Scenario: Existing spool available
- **WHEN** the events request matches a valid spool / completed async result
- **THEN** the endpoint SHALL return results without rerunning Oracle work

#### Scenario: No spool available
- **WHEN** the events request has no reusable spool
- **THEN** the endpoint SHALL enqueue the events work to RQ and return HTTP 202 for the async-capable path

### Requirement: MSD aggregation SHALL be computed from spool-backed runtime
For `profile=mid_section_defect`, events aggregation SHALL be computed from spool-backed DuckDB/runtime logic instead of large in-memory pandas aggregation.

#### Scenario: MSD aggregation runs from staged dataset
- **WHEN** `POST /api/trace/events` is called with `profile=mid_section_defect`
- **THEN** the aggregation stage SHALL read from the staged trace dataset / runtime view instead of materializing a large pandas frame in the web worker
- **THEN** any downstream detail or export flow SHALL be able to reference the same canonical staged dataset identity

### Requirement: Guard retirement SHALL be gated by path retirement
CID limits and sync RSS rejection on trace events SHALL only be removed once all relevant heavy execution is guaranteed to go through the spool-safe path.

#### Scenario: Legacy sync path still exists
- **WHEN** a sync compatibility path remains
- **THEN** protection guards SHALL remain in place for that path

#### Scenario: Sync path retired
- **WHEN** all heavy trace events execution is routed through RQ/spool
- **THEN** the legacy CID and RSS guards MAY be removed
