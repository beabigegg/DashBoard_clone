## MODIFIED Requirements

### Requirement: Shared async job service SHALL provide job enqueue capability
The `async_query_job_service` module SHALL provide a generic `enqueue_job()` function that enqueues a callable to a named RQ queue with configurable timeout and TTL. The function SHALL require a server-derived `owner` token and persist it into job metadata so that downstream lifecycle operations (abandon, status) can authorise the caller.

#### Scenario: Successful enqueue
- **WHEN** `enqueue_job(queue_name="reject-query", worker_fn=fn, job_id="reject-abc123", kwargs={...}, job_timeout=1800, result_ttl=3600, owner="alice")` is called
- **THEN** the function SHALL enqueue `fn` to the `reject-query` RQ queue
- **THEN** the function SHALL write initial job metadata to Redis HSET at key `{prefix}:job:{job_id}:meta`
- **THEN** the metadata SHALL include `status=queued`, `created_at`, `queue_name`, `owner=alice`
- **THEN** the function SHALL return `(job_id, None)` on success

#### Scenario: Owner argument is required
- **WHEN** `enqueue_job(...)` is called without an `owner` keyword argument
- **THEN** the function SHALL raise `TypeError`
- **THEN** no job SHALL be enqueued and no Redis metadata SHALL be written

#### Scenario: RQ unavailable
- **WHEN** `enqueue_job()` is called with a valid owner but RQ is not installed or Redis is unreachable
- **THEN** the function SHALL return `(None, "async queue unavailable")`
- **THEN** no exception SHALL be raised

#### Scenario: Enqueue failure
- **WHEN** `enqueue_job()` is called with a valid owner but the RQ enqueue operation fails
- **THEN** the function SHALL return `(None, "<error message>")`
- **THEN** the job metadata SHALL be updated with `status=failed` and `error` field
- **THEN** the previously-written `owner` field SHALL remain in the metadata

### Requirement: Shared async job service SHALL provide job status query
The module SHALL provide `get_job_status(prefix, job_id)` that reads job metadata from Redis. The returned dict SHALL include the `owner` field when present.

#### Scenario: Job exists and is running
- **WHEN** `get_job_status("reject", "abc123")` is called and the job is in progress
- **THEN** the function SHALL return a dict with `job_id`, `status=running`, `progress`, `created_at`, `elapsed_seconds`, `owner`

#### Scenario: Job completed
- **WHEN** `get_job_status("reject", "abc123")` is called and the job has finished
- **THEN** the returned dict SHALL include `status=completed`, `query_id`, `completed_at`, `elapsed_seconds`, `owner`

#### Scenario: Job not found
- **WHEN** `get_job_status("reject", "nonexistent")` is called
- **THEN** the function SHALL return `None`

## ADDED Requirements

### Requirement: Server SHALL derive owner identity from session, never from request body
A new helper `get_owner_token()` in `mes_dashboard.core.permissions` SHALL return a stable, server-controlled identity for the current request. Endpoints that enqueue or abandon async jobs SHALL use this helper instead of trusting any client-supplied owner field.

#### Scenario: Logged-in user owner token
- **WHEN** `get_owner_token()` is called inside a request whose Flask session contains `session["user"]["username"] = "alice"`
- **THEN** the function SHALL return `"alice"`

#### Scenario: Anonymous session lazy mint
- **WHEN** `get_owner_token()` is called inside a request with no logged-in user and no existing `session["mes_owner_token"]`
- **THEN** the function SHALL generate a uuid4 hex, store it as `session["mes_owner_token"]`, and return it
- **THEN** subsequent calls within the same browser session SHALL return the same token

#### Scenario: Anonymous session reuses minted token
- **WHEN** `get_owner_token()` is called and `session["mes_owner_token"]` already exists
- **THEN** the function SHALL return the existing value without regeneration

### Requirement: Async job abandon SHALL authorise the caller against server-derived owner
The `POST /api/job/<job_id>/abandon` endpoint SHALL determine the caller's owner via `get_owner_token()`, compare it to `meta["owner"]`, and reject any mismatch. The endpoint SHALL ignore any `owner` field present in the request body.

#### Scenario: Owner matches
- **WHEN** the caller's session token equals `meta["owner"]` and the job is in an abandonable state
- **THEN** the endpoint SHALL mark the job `abandoned` and return HTTP 200

#### Scenario: Owner mismatch
- **WHEN** the caller's session token differs from `meta["owner"]`
- **THEN** the endpoint SHALL return HTTP 403 with error code `FORBIDDEN`
- **THEN** the job status SHALL NOT change

#### Scenario: Missing owner in metadata (legacy job, fail-closed)
- **WHEN** `meta["owner"]` is absent or empty
- **THEN** the endpoint SHALL return HTTP 403 with error code `FORBIDDEN`
- **THEN** the job status SHALL NOT change

#### Scenario: Body owner field is ignored
- **WHEN** the request body contains `{"prefix": "reject", "owner": "mallory"}` and the session token is `"alice"`
- **THEN** the endpoint SHALL evaluate `"alice"` against `meta["owner"]` and ignore `"mallory"`
