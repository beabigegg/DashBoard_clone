## MODIFIED Requirements

### Requirement: Material Trace page SHALL provide loading and error states
The page SHALL provide clear feedback during loading and error conditions. The backend async job enqueue SHALL target the correct RQ worker queue so that jobs are executed and status transitions occur.

#### Scenario: Loading state
- **WHEN** a query is in progress
- **THEN** a loading indicator SHALL be visible
- **THEN** the query button SHALL be disabled

#### Scenario: API error
- **WHEN** the API returns an error
- **THEN** a red error banner SHALL display the error message

#### Scenario: Error cleared on new query
- **WHEN** user initiates a new query
- **THEN** previous error and warning banners SHALL be cleared

#### Scenario: Async job enqueue targets worker queue
- **WHEN** a forward query has no spool hit and an async RQ job is enqueued
- **THEN** the job SHALL be enqueued to the queue monitored by `TRACE_WORKER_QUEUE` (default: `trace-events`)
- **THEN** the queue name SHALL be read from the `TRACE_WORKER_QUEUE` environment variable with fallback `trace-events`
- **THEN** the RQ worker SHALL pick up and execute the job within its normal processing cycle

#### Scenario: Async job completes and frontend receives results
- **WHEN** the RQ worker completes the material-trace spool job
- **THEN** the job status in Redis SHALL transition to `completed` with a `query_hash`
- **THEN** the frontend polling SHALL detect the completion and load paginated results from the DuckDB spool
