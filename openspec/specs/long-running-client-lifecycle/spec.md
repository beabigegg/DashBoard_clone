# long-running-client-lifecycle Specification

## Purpose
TBD - created by archiving change qa-coverage-hardening. Update Purpose after archive.
## Requirements
### Requirement: Session expiry on long-open pages SHALL surface a re-authentication envelope
When a long-open page's session expires, subsequent requests SHALL receive an explicit envelope that allows the frontend to pause auto-refresh and prompt re-login.

#### Scenario: Auto-refresh after session expiry
- **WHEN** `useAutoRefresh` polls an API and the session has expired
- **THEN** the response envelope SHALL be `{ success:false, error:{ code:'SESSION_EXPIRED', message:... }, meta:{ reauth_url: ... } }` with HTTP 401
- **THEN** `useAutoRefresh` SHALL stop the refresh timer AND display the re-login modal AND SHALL NOT continue polling

### Requirement: Auto-refresh composable SHALL release all resources on unmount
`useAutoRefresh` SHALL clean up timers and abort controllers when the component unmounts, regardless of document visibility state.

#### Scenario: Unmount cleans up
- **WHEN** a component using `useAutoRefresh` unmounts
- **THEN** all timers SHALL be cleared AND all pending fetches SHALL be aborted

#### Scenario: No memory leak after many refresh cycles
- **WHEN** a component runs `useAutoRefresh` through 100 refresh cycles and then unmounts
- **THEN** no residual timers, controllers, or reactive state SHALL remain

#### Scenario: Page visibility pause and resume
- **WHEN** the document transitions to `hidden`
- **THEN** the refresh timer SHALL pause
- **WHEN** the document transitions back to `visible`
- **THEN** the refresh timer SHALL resume without duplicating the immediate tick

### Requirement: Async query jobs SHALL survive client disconnect with bounded resource usage
Server-side async query jobs SHALL continue or terminate cleanly when the originating client disconnects, without leaving orphan state.

#### Scenario: Client disconnect during sync query
- **WHEN** a client disconnects while an in-progress sync request is executing
- **THEN** the worker SHALL detect the disconnect (via `request.environ` or equivalent) and release the Oracle cursor within 5 seconds

#### Scenario: Orphan async job TTL
- **WHEN** an RQ async job is not polled or claimed by any client for longer than `JOB_RESULT_TTL`
- **THEN** the job's result, Redis metadata, and spool parquet SHALL be reclaimed by the cleanup worker

#### Scenario: Worker hard timeout releases Oracle cursor
- **WHEN** an RQ worker exceeds its hard `job_timeout`
- **THEN** the Oracle connection SHALL be returned to the pool AND the pool's active count SHALL not increase over the 100-job baseline

### Requirement: Client SHALL proactively abandon unfinished jobs on page unload
The frontend SHALL send a best-effort abandonment signal for in-flight async jobs when the user closes or navigates away from the page.

#### Scenario: Beforeunload sends abandon
- **WHEN** the user closes a tab while an async job is pending
- **THEN** the frontend SHALL invoke `POST /api/job/<id>/abandon` via `navigator.sendBeacon` or equivalent
- **THEN** the server SHALL mark the job abandoned and schedule expedited cleanup

#### Scenario: Abandonment requires session ownership
- **WHEN** a client calls `POST /api/job/<id>/abandon` for a job it does not own
- **THEN** the server SHALL return `{ success:false, error:{ code:'FORBIDDEN' } }` with HTTP 403

### Requirement: RQ worker crash SHALL be reconciled to a terminal job state
Jobs whose worker crashed SHALL be marked failed rather than remaining in `running` indefinitely.

#### Scenario: SIGKILL mid-job reconciled
- **WHEN** an RQ worker is SIGKILLed while executing a job
- **THEN** the next sweep (scheduled cleanup or RQ `StartedJobRegistry.cleanup()`) SHALL mark the job as `failed` with a diagnostic reason

#### Scenario: Worker restart does not rerun completed jobs
- **WHEN** an RQ worker is restarted after completing a job
- **THEN** the job SHALL NOT be re-executed

### Requirement: Dataset schema version bumps SHALL invalidate stale query IDs
When the service deploys a dataset schema bump, previously issued `query_id` / `dataset_id` values SHALL be invalidated rather than silently returning old-shape results.

#### Scenario: Stale query_id after schema bump
- **WHEN** a client holds a `query_id` issued before a schema version bump and requests the corresponding view
- **THEN** the server SHALL return `{ success:false, error:{ code:'DATASET_VERSION_MISMATCH' }, meta:{ required_action:'requery' } }` with HTTP 410
- **THEN** the frontend SHALL show a version-drift banner and trigger a re-query

### Requirement: Envelope meta SHALL include app_version for drift detection
All `success_response` and `error_response` envelopes SHALL include `meta.app_version` so the frontend can detect deployment drift on long-open pages.

#### Scenario: Meta contains app_version
- **WHEN** any helper in `core/response.py` produces a response
- **THEN** `meta.app_version` SHALL contain the current deployed application version string

