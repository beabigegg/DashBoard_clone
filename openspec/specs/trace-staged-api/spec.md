## Purpose
Staged trace API for seed-resolve, lineage, and events pipeline with rate limiting, caching, and memory management.
## Requirements
### Requirement: Staged trace API SHALL expose seed-resolve endpoint
`POST /api/trace/seed-resolve` SHALL resolve seed lots based on the provided profile and parameters.

#### Scenario: query_tool profile seed resolve
- **WHEN** request body contains `{ "profile": "query_tool", "params": { "resolve_type": "lot_id", "values": [...] } }`
- **THEN** the endpoint SHALL call existing lot resolve logic and return `{ "stage": "seed-resolve", "seeds": [...], "seed_count": N, "cache_key": "trace:{hash}" }`
- **THEN** each seed object SHALL contain `container_id`, `container_name`, and `lot_id`

#### Scenario: mid_section_defect profile seed resolve
- **WHEN** request body contains `{ "profile": "mid_section_defect", "params": { "date_range": [...], "workcenter": "..." } }`
- **THEN** the endpoint SHALL call TMTT detection logic and return seed lots in the same response format

#### Scenario: Empty seed result
- **WHEN** seed resolution finds no matching lots
- **THEN** the endpoint SHALL return HTTP 200 with `{ "stage": "seed-resolve", "seeds": [], "seed_count": 0, "cache_key": "trace:{hash}" }`
- **THEN** the error code `SEED_RESOLVE_EMPTY` SHALL NOT be used for empty results (reserved for resolution failures)

#### Scenario: Invalid profile
- **WHEN** request body contains an unrecognized `profile` value
- **THEN** the endpoint SHALL return HTTP 400 with `{ "error": "...", "code": "INVALID_PROFILE" }`

### Requirement: Staged trace API SHALL expose lineage endpoint
`POST /api/trace/lineage` SHALL resolve lineage graph for provided container IDs using `LineageEngine`.

#### Scenario: Normal lineage resolution
- **WHEN** request body contains `{ "profile": "query_tool", "container_ids": [...] }`
- **THEN** the endpoint SHALL call `LineageEngine.resolve_full_genealogy()` and return `{ "stage": "lineage", "ancestors": {...}, "merges": {...}, "total_nodes": N }`

#### Scenario: Lineage result caching with idempotency
- **WHEN** two requests with the same `container_ids` set (regardless of order) arrive
- **THEN** the cache key SHALL be computed as `trace:lineage:{sorted_cids_hash}`
- **THEN** the second request SHALL return cached result from L2 Redis (TTL = 300s)

#### Scenario: Lineage timeout
- **WHEN** lineage resolution exceeds 10 seconds
- **THEN** the endpoint SHALL return HTTP 504 with `{ "error": "...", "code": "LINEAGE_TIMEOUT" }`

### Requirement: Staged trace API SHALL expose events endpoint
`POST /api/trace/events` SHALL query events for specified domains using `EventFetcher`.

#### Scenario: Normal events query
- **WHEN** request body contains `{ "profile": "query_tool", "container_ids": [...], "domains": ["history", "materials"] }`
- **THEN** the endpoint SHALL return `{ "stage": "events", "results": { "history": { "data": [...], "count": N }, "materials": { "data": [...], "count": N } }, "aggregation": null }`

#### Scenario: mid_section_defect profile with aggregation
- **WHEN** request body contains `{ "profile": "mid_section_defect", "container_ids": [...], "domains": ["upstream_history"] }`
- **THEN** the endpoint SHALL automatically run aggregation logic after event fetching
- **THEN** the response `aggregation` field SHALL contain the aggregated results (not null)

#### Scenario: Partial domain failure
- **WHEN** one domain query fails while others succeed
- **THEN** the endpoint SHALL return HTTP 200 with `{ "error": "...", "code": "EVENTS_PARTIAL_FAILURE" }`
- **THEN** the response SHALL include successfully fetched domains in `results` and list failed domains in `failed_domains`

### Requirement: All staged trace endpoints SHALL apply rate limiting and caching
Every `/api/trace/*` endpoint SHALL use `configured_rate_limit()` and L2 Redis caching.

#### Scenario: Rate limit exceeded on any trace endpoint
- **WHEN** a client exceeds the configured request budget for a trace endpoint
- **THEN** the endpoint SHALL return HTTP 429 with a `Retry-After` header
- **THEN** the body SHALL contain `{ "error": "...", "meta": { "retry_after_seconds": N } }`

#### Scenario: Cache hit on trace endpoint
- **WHEN** a request matches a cached result in L2 Redis (TTL = 300s)
- **THEN** the cached result SHALL be returned without executing backend logic
- **THEN** Oracle DB connection pool SHALL NOT be consumed

### Requirement: cache_key parameter SHALL be used for logging correlation only
The optional `cache_key` field in request bodies SHALL be used solely for logging and tracing correlation.

#### Scenario: cache_key provided in request
- **WHEN** a request includes `cache_key` from a previous stage response
- **THEN** the value SHALL be logged for correlation purposes
- **THEN** the value SHALL NOT influence cache lookup or rate limiting logic

#### Scenario: cache_key omitted in request
- **WHEN** a request omits the `cache_key` field
- **THEN** the endpoint SHALL function normally without any degradation

### Requirement: Existing `GET /api/mid-section-defect/analysis` SHALL remain compatible
The existing analysis endpoint (GET method) SHALL internally delegate to the staged pipeline while maintaining identical external behavior.

#### Scenario: Legacy analysis endpoint invocation
- **WHEN** a client calls `GET /api/mid-section-defect/analysis` with existing query parameters
- **THEN** the endpoint SHALL internally execute seed-resolve → lineage → events + aggregation
- **THEN** the response format SHALL be identical to the pre-refactoring output
- **THEN** a golden test SHALL verify output equivalence

### Requirement: Trace events endpoint SHALL limit domain concurrency
The `/api/trace/events` endpoint SHALL use `TRACE_EVENTS_MAX_WORKERS` to control how many domains execute concurrently.

#### Scenario: Default domain concurrency
- **WHEN** the events endpoint dispatches domain queries
- **THEN** the default `TRACE_EVENTS_MAX_WORKERS` SHALL be 2 (env: `TRACE_EVENTS_MAX_WORKERS`)

### Requirement: Trace events endpoint SHALL manage memory for large queries
The events endpoint SHALL proactively release memory after processing large CID sets.

#### Scenario: Early release of grouped domain results
- **WHEN** MSD aggregation completes using `raw_domain_results`
- **THEN** the `raw_domain_results` reference SHALL be deleted immediately after aggregation
- **THEN** for non-MSD profiles, `raw_domain_results` SHALL be deleted after result assembly

#### Scenario: Garbage collection for large CID sets
- **WHEN** the events endpoint completes processing and the CID count exceeds 10000
- **THEN** `gc.collect()` SHALL be called to prompt Python garbage collection

#### Scenario: Large CID set skips route-level cache
- **WHEN** the events endpoint completes for a non-MSD profile and CID count exceeds 10000
- **THEN** the route-level events cache write SHALL be skipped

