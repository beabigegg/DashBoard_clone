## ADDED Requirements

### Requirement: Trace API SHALL expose NDJSON stream endpoint for job results
`GET /api/trace/job/{job_id}/stream` SHALL return job results as NDJSON (Newline Delimited JSON) stream.

#### Scenario: Stream completed job result
- **WHEN** a client requests stream for a completed job
- **THEN** the endpoint SHALL return `Content-Type: application/x-ndjson`
- **THEN** the response SHALL contain ordered NDJSON lines: `meta` → `domain_start` → `records` batches → `domain_end` → `aggregation` (if applicable) → `complete`
- **THEN** each `records` line SHALL contain at most `TRACE_STREAM_BATCH_SIZE` (env, default: 5000) records

#### Scenario: Stream for non-completed job
- **WHEN** a client requests stream for a non-completed job
- **THEN** the endpoint SHALL return HTTP 409 with `{ "error": "...", "code": "JOB_NOT_COMPLETE" }`

### Requirement: Job result pagination SHALL support domain-level offset/limit
`GET /api/trace/job/{job_id}/result` SHALL support fine-grained pagination per domain.

#### Scenario: Paginated domain result
- **WHEN** a client requests `?domain=history&offset=0&limit=5000`
- **THEN** the endpoint SHALL return only the specified slice of records for that domain
- **THEN** the response SHALL include `total` count for the domain
