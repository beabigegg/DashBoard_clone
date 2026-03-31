## Why

Material-trace forward query (正向查詢) always times out with "查詢逾時，請重試" because the async RQ job is enqueued to a `"default"` queue that no RQ worker listens on. The job sits in the queue indefinitely, the frontend polls until it exceeds the 150-attempt limit (~5 minutes), and the user sees a timeout error. This is a queue-name mismatch introduced when material-trace was migrated to the async spool architecture — the queue name was never updated from the placeholder `"default"` to the actual worker queue.

## What Changes

- Fix the RQ queue name in `material_trace_routes.py` from hard-coded `"default"` to the `TRACE_WORKER_QUEUE` (defaults to `trace-events`) that the RQ worker actually listens on.
- Extract the queue name into a constant (consistent with how `reject_query_job_service`, `trace_lineage_job_service`, and `mid_section_defect_service` all reference their queue via env-var-backed constants).

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `material-trace-page`: The async forward query must enqueue to the correct RQ worker queue so that jobs are actually picked up and executed.

## Impact

- **Backend route:** `src/mes_dashboard/routes/material_trace_routes.py` — change `queue_name` argument in `enqueue_job()` call (line 154).
- **Backend service (optional):** `src/mes_dashboard/services/material_trace_service.py` — add a `MATERIAL_TRACE_QUEUE` constant referencing `TRACE_WORKER_QUEUE` env var, consistent with other services.
- **No frontend changes required** — the polling and display logic is correct; only the backend queue routing is broken.
- **No breaking changes** — this is a bug fix restoring intended behavior.
