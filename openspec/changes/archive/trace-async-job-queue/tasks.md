## 1. Dependencies

- [x] 1.1 Add `rq>=1.16.0,<2.0.0` to `requirements.txt`
- [x] 1.2 Add `rq>=1.16.0,<2.0.0` to pip dependencies in `environment.yml`

## 2. Trace Job Service

- [x] 2.1 Create `src/mes_dashboard/services/trace_job_service.py` with `enqueue_trace_events_job()`, `get_job_status()`, `get_job_result()`
- [x] 2.2 Implement `execute_trace_events_job()` function (RQ worker entry point): runs EventFetcher + optional MSD aggregation, stores result in Redis with TTL
- [x] 2.3 Add job metadata tracking: `trace:job:{job_id}:meta` Redis key with `{profile, cid_count, domains, status, progress, created_at, completed_at}`
- [x] 2.4 Add unit tests for trace_job_service (13 tests: enqueue, status, result, worker execution, flatten)

## 3. Async API Endpoints

- [x] 3.1 Modify `events()` in `trace_routes.py`: when `len(container_ids) > TRACE_ASYNC_CID_THRESHOLD` and async available, call `enqueue_trace_events_job()` and return HTTP 202
- [x] 3.2 Add `GET /api/trace/job/<job_id>` endpoint: return job status from `get_job_status()`
- [x] 3.3 Add `GET /api/trace/job/<job_id>/result` endpoint: return job result from `get_job_result()` with optional `domain`, `offset`, `limit` query params
- [x] 3.4 Add rate limiting to job status/result endpoints (60 req/60s)
- [x] 3.5 Add unit tests for async endpoints (8 tests: async routing, sync fallback, 413 fallback, job status/result)

## 4. Deployment

- [x] 4.1 Create `deploy/mes-dashboard-trace-worker.service` systemd unit (MemoryHigh=3G, MemoryMax=4G)
- [x] 4.2 Update `scripts/start_server.sh`: add `start_rq_worker`/`stop_rq_worker`/`rq_worker_status` functions
- [x] 4.3 Update `scripts/deploy.sh`: add trace worker systemd install instructions
- [x] 4.4 Update `.env.example`: uncomment and add `TRACE_WORKER_ENABLED`, `TRACE_ASYNC_CID_THRESHOLD`, `TRACE_JOB_TTL_SECONDS`, `TRACE_JOB_TIMEOUT_SECONDS`, `TRACE_WORKER_COUNT`, `TRACE_WORKER_QUEUE`

## 5. Frontend Integration

- [x] 5.1 Modify `useTraceProgress.js`: detect async response (`eventsPayload.async === true`), switch to job polling mode
- [x] 5.2 Add `pollJobUntilComplete()` helper: poll `GET /api/trace/job/{job_id}` every 3s, max 30 minutes
- [x] 5.3 Add `job_progress` reactive state for UI: `{ active, job_id, status, elapsed_seconds, progress }`
- [x] 5.4 Add error handling: job failed (`JOB_FAILED`), polling timeout (`JOB_POLL_TIMEOUT`), abort support

## 6. Verification

- [x] 6.1 Run `python -m pytest tests/ -v` — 1090 passed, 152 skipped
- [x] 6.2 Run `cd frontend && npm run build` — frontend builds successfully
- [x] 6.3 Verify rq installed: `python -c "import rq; print(rq.VERSION)"` → 1.16.2
