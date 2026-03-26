## ADDED Requirements

### Requirement: MSD analysis SHALL support asynchronous execution via RQ
The `mid_section_defect_routes.py` analysis endpoint SHALL detect when the query is expected to be slow and enqueue it as a background job.

#### Scenario: Async path triggered
- **WHEN** `POST /api/mid-section-defect/analysis` is called and RQ workers are available
- **THEN** the route SHALL enqueue the analysis pipeline to the `msd-analysis` RQ queue
- **THEN** the route SHALL return HTTP 202 with `{"async": true, "job_id": "<uuid>", "status_url": "/api/mid-section-defect/analysis/job/<job_id>"}`

#### Scenario: Sync fallback when RQ unavailable
- **WHEN** `POST /api/mid-section-defect/analysis` is called but `is_async_available()` returns False
- **THEN** the route SHALL execute synchronously (existing behavior)
- **THEN** the response SHALL be the normal 200 JSON result

#### Scenario: Cache hit bypasses async
- **WHEN** the analysis result is already cached (cache_get returns non-None)
- **THEN** the route SHALL return the cached result immediately (200)
- **THEN** no RQ job SHALL be enqueued

### Requirement: MSD analysis job service SHALL provide enqueue/status/result
A new `msd_query_job_service.py` SHALL provide MSD-specific wrappers around `async_query_job_service`.

#### Scenario: Enqueue MSD analysis
- **WHEN** `enqueue_msd_analysis(start_date, end_date, station, direction, loss_reasons)` is called
- **THEN** the function SHALL call `enqueue_job(queue_name="msd-analysis", worker_fn=_execute_msd_analysis, ...)`
- **THEN** the function SHALL return `(job_id, None)` on success

#### Scenario: Worker executes pipeline
- **WHEN** the RQ worker picks up an MSD analysis job
- **THEN** it SHALL call `query_analysis()` with the provided parameters
- **THEN** on success it SHALL store the result via `cache_set()` and call `complete_job(query_id=cache_key)`
- **THEN** on failure it SHALL call `complete_job(error=str(exc))` and re-raise

### Requirement: MSD analysis job status and result endpoints
Routes SHALL provide job status and result retrieval.

#### Scenario: Job status query
- **WHEN** `GET /api/mid-section-defect/analysis/job/<job_id>` is called
- **THEN** it SHALL return the job metadata (status, progress, elapsed_seconds)

#### Scenario: Job result retrieval
- **WHEN** `GET /api/mid-section-defect/analysis/job/<job_id>/result` is called and job is completed
- **THEN** it SHALL load the cached analysis result and return it

### Requirement: MSD worker systemd unit
A systemd service unit SHALL be provided for the MSD analysis RQ worker.

#### Scenario: Worker deployment
- **GIVEN** `deploy/mes-dashboard-msd-worker.service` exists
- **THEN** it SHALL configure `rq worker msd-analysis` with `Restart=always`, `RestartSec=10`, `MemoryMax=4G`
- **THEN** `scripts/start_server.sh` SHALL include start/stop for the MSD worker

### Requirement: Frontend SHALL use async polling for MSD analysis
The MSD analysis Vue component SHALL use `useAsyncJobPolling` when receiving a 202 response.

#### Scenario: Async response handling
- **WHEN** the frontend receives HTTP 202 with `{async: true, job_id, status_url}`
- **THEN** it SHALL start polling `status_url` using `useAsyncJobPolling`
- **THEN** it SHALL display a loading/progress indicator during polling
- **THEN** on completion it SHALL fetch and render the result
