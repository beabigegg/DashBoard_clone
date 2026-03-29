## ADDED Requirements

### Requirement: Async query job service SHALL serve as the Type B miss re-dispatch entry point
The async query job service SHALL be the designated re-dispatch mechanism for Type B domains (`reject-history`, `material-trace`, `MSD`) when a view miss (HTTP 410) occurs. The client SHALL use this service to enqueue a new primary query job after receiving a 410.

This service SHALL NOT be invoked automatically by view endpoints. The client is responsible for calling the appropriate domain query endpoint (which internally uses this service) after receiving a 410.

#### Scenario: Type B domain dispatches async job after view miss
- **WHEN** a Type B domain's view endpoint returns HTTP 410 `cache_expired`
- **THEN** the client SHALL POST to the domain's query endpoint with original query parameters
- **THEN** the domain query route SHALL call `should_use_async()` to determine the execution path
- **THEN** if `should_use_async()` returns `True`, the route SHALL call `enqueue_job()` and return HTTP 202 with `{ job_id }`
- **THEN** the client SHALL use `get_job_status(job_id)` to poll until completion

#### Scenario: Job completion provides query_id for view load
- **WHEN** an async job completes successfully
- **THEN** the job result SHALL include the `query_id` of the completed query
- **THEN** the client SHALL use this `query_id` to request the view endpoint
- **THEN** the view endpoint SHALL return the computed result from the spool
