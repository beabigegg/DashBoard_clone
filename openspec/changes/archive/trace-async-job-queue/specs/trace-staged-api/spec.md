## ADDED Requirements

### Requirement: Trace events endpoint SHALL support asynchronous job execution
The `/api/trace/events` endpoint SHALL automatically route large CID requests to an async job queue.

#### Scenario: CID count exceeds async threshold
- **WHEN** the events endpoint receives a request with `container_ids` count exceeding `TRACE_ASYNC_CID_THRESHOLD` (env: `TRACE_ASYNC_CID_THRESHOLD`, default: 20000)
- **THEN** the endpoint SHALL enqueue the request to the `trace-events` RQ queue
- **THEN** the endpoint SHALL return HTTP 202 with `{ "stage": "events", "async": true, "job_id": "...", "status_url": "/api/trace/job/{job_id}" }`

#### Scenario: CID count within sync threshold
- **WHEN** the events endpoint receives a request with `container_ids` count ≤ `TRACE_ASYNC_CID_THRESHOLD`
- **THEN** the endpoint SHALL process synchronously as before

### Requirement: Trace API SHALL expose job status endpoint
`GET /api/trace/job/{job_id}` SHALL return the current status of an async trace job.

#### Scenario: Job status query
- **WHEN** a client queries job status with a valid job_id
- **THEN** the endpoint SHALL return `{ "job_id": "...", "status": "queued|started|finished|failed", "progress": {...}, "created_at": "...", "elapsed_seconds": N }`

#### Scenario: Job not found
- **WHEN** a client queries job status with an unknown or expired job_id
- **THEN** the endpoint SHALL return HTTP 404 with `{ "error": "...", "code": "JOB_NOT_FOUND" }`

### Requirement: Trace API SHALL expose job result endpoint
`GET /api/trace/job/{job_id}/result` SHALL return the result of a completed async trace job.

#### Scenario: Completed job result
- **WHEN** a client requests result for a completed job
- **THEN** the endpoint SHALL return the same response format as the synchronous events endpoint
- **THEN** optional query params `domain`, `offset`, `limit` SHALL support pagination

#### Scenario: Job not yet completed
- **WHEN** a client requests result for a non-completed job
- **THEN** the endpoint SHALL return HTTP 409 with `{ "error": "...", "code": "JOB_NOT_COMPLETE", "status": "queued|started" }`

### Requirement: Async trace jobs SHALL have TTL and timeout
Job results SHALL expire after a configurable TTL, and execution SHALL be bounded by a timeout.

#### Scenario: Job result TTL
- **WHEN** a trace job completes (success or failure)
- **THEN** the result SHALL be stored in Redis with TTL = `TRACE_JOB_TTL_SECONDS` (env, default: 3600)

#### Scenario: Job execution timeout
- **WHEN** a trace job exceeds `TRACE_JOB_TIMEOUT_SECONDS` (env, default: 1800)
- **THEN** RQ SHALL terminate the job and mark it as failed
