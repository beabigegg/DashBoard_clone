## Purpose

Async RQ worker infrastructure for production-history queries, offloading heavy synchronous queries from Gunicorn workers to dedicated RQ worker processes.

## Requirements

### Requirement: Production History job service
The system SHALL provide a `production_history_job_service` module that bridges the production-history primary query to an RQ background worker. The module SHALL expose `should_use_async()`, `enqueue_production_history_query()`, and `execute_production_history_job()` functions following the same contract as `reject_query_job_service`.

#### Scenario: Enqueue succeeds when RQ is available
- **WHEN** `enqueue_production_history_query(params)` is called and RQ worker is available
- **THEN** the function SHALL return `(job_id, None)` and the job SHALL be enqueued to the `production-history-query` queue

#### Scenario: Enqueue fails gracefully when RQ is unavailable
- **WHEN** `enqueue_production_history_query(params)` is called and RQ worker is unavailable
- **THEN** the function SHALL return `(None, error_message)` without raising an exception

#### Scenario: Worker entry point executes query and spools result
- **WHEN** `execute_production_history_job(job_id, params)` runs in the RQ worker
- **THEN** it SHALL call the existing `query_production_history` service function, update job progress via `update_job_progress`, and call `complete_job` on completion

#### Scenario: Worker entry point skips Oracle when cache exists
- **WHEN** `execute_production_history_job` runs and the spool/cache already contains the result
- **THEN** it SHALL skip the Oracle query and immediately call `complete_job` with the existing query_id

### Requirement: Production History route returns 202 for async queries
The `POST /api/production-history/query` endpoint SHALL return HTTP 202 with `{ async: true, job_id, status_url, dataset_id }` when the query is routed to the RQ worker.

#### Scenario: Spool hit returns 200 immediately
- **WHEN** a query request arrives and the spool/cache already has the result
- **THEN** the route SHALL return HTTP 200 with the full result (unchanged behavior)

#### Scenario: Spool miss with RQ available returns 202
- **WHEN** a query request arrives, spool misses, and `is_async_available()` returns True
- **THEN** the route SHALL enqueue the job and return HTTP 202 with `{ async: true, job_id, status_url }`

#### Scenario: Spool miss with RQ unavailable falls back to sync
- **WHEN** a query request arrives, spool misses, and `is_async_available()` returns False
- **THEN** the route SHALL execute the query synchronously (original behavior)

### Requirement: Production History job status endpoint
The system SHALL expose `GET /api/production-history/job/<job_id>` that returns the job's current status (`queued`, `started`, `running`, `completed`, `failed`).

#### Scenario: Job in progress returns status
- **WHEN** a GET request is made for a running job
- **THEN** the endpoint SHALL return `{ status: "running", progress: "..." }`

#### Scenario: Job completed returns query_id
- **WHEN** a GET request is made for a completed job
- **THEN** the endpoint SHALL return `{ status: "completed", query_id: "..." }` so the frontend can load the view

#### Scenario: Job not found returns 404
- **WHEN** a GET request is made for a non-existent job_id
- **THEN** the endpoint SHALL return HTTP 404

### Requirement: Production History frontend handles 202 polling
The `useProductionHistory.js` composable SHALL detect HTTP 202 responses and poll the job status URL using `pollJobUntilComplete` from `useAsyncJobPolling.js`.

#### Scenario: Frontend receives 202 and starts polling
- **WHEN** `runQuery` receives a 202 response with `{ async: true, job_id, status_url }`
- **THEN** it SHALL call `pollJobUntilComplete(status_url)` and show a loading/progress state

#### Scenario: Polling completes and loads view data
- **WHEN** `pollJobUntilComplete` resolves with `status: "completed"`
- **THEN** the composable SHALL use the returned `dataset_id` / `query_id` to load the view data via the existing page/matrix endpoints

#### Scenario: Polling can be cancelled
- **WHEN** the user triggers a new query while polling is in progress
- **THEN** the previous polling SHALL be aborted via AbortController

### Requirement: Production History RQ worker process
The `start_server.sh` SHALL manage a dedicated RQ worker process for the `production-history-query` queue, following the same pattern as the reject worker.

#### Scenario: Worker starts with isolated DB pool
- **WHEN** the production-history worker is started
- **THEN** it SHALL launch with `DB_POOL_SIZE=2 DB_MAX_OVERFLOW=1` environment variables

#### Scenario: Worker is controlled by enable flag
- **WHEN** `RQ_PRODUCTION_HISTORY_WORKER_ENABLED` is set to `false`
- **THEN** the worker SHALL not be started and status SHALL show `DISABLED`

### Requirement: Production History async environment variables
The system SHALL support the following environment variables for the production-history async worker.

#### Scenario: Default configuration
- **WHEN** no environment variables are set
- **THEN** the defaults SHALL be: `PRODUCTION_HISTORY_ASYNC_ENABLED=true`, `PRODUCTION_HISTORY_WORKER_QUEUE=production-history-query`, `PRODUCTION_HISTORY_JOB_TTL_SECONDS=3600`, `PRODUCTION_HISTORY_JOB_TIMEOUT_SECONDS=1800`, `RQ_PRODUCTION_HISTORY_WORKER_ENABLED=true`

### Requirement: Remove production-history synchronous overload guard
The `heavy_query_overloaded` RuntimeError handling in `production_history_routes.py` SHALL be removed, as the RQ worker mechanism replaces this concurrency control.

#### Scenario: Overload guard no longer triggers 503
- **WHEN** the async worker path is active
- **THEN** the route SHALL NOT check for `heavy_query_overloaded` or return 503 for overload — concurrency is controlled by the single-worker queue
