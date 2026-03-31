## Context

Material-trace forward query uses the async spool architecture (Task 8.3/8.4): the route enqueues an RQ job, the frontend polls for completion, and DuckDB serves paginated results from the parquet spool.

The RQ worker started by `start_server.sh` listens on the `trace-events` queue (controlled by `TRACE_WORKER_QUEUE` env var). However, `material_trace_routes.py` enqueues to `queue_name="default"` — a queue no worker monitors. The job is created in Redis but never executed.

All other async services follow the established pattern of referencing their queue via an env-var-backed module constant:
- `trace_lineage_job_service.py` → `TRACE_WORKER_QUEUE` → `trace-events`
- `reject_query_job_service.py` → `REJECT_WORKER_QUEUE` → `reject-query`
- `mid_section_defect_service.py` / `msd_lineage_job_service.py` → `MSD_COMPAT_QUEUE` / `MSD_LINEAGE_QUEUE` → `msd-analysis`

## Goals / Non-Goals

**Goals:**
- Fix material-trace forward query so that async jobs are picked up by the RQ worker
- Align the queue-name pattern with the rest of the codebase (env-var-backed constant)

**Non-Goals:**
- Introducing a dedicated worker or queue for material-trace (reuse existing `trace-events` worker)
- Changing the async polling, spool, or DuckDB pagination logic (these work correctly)
- Modifying frontend behavior

## Decisions

### Decision 1: Reuse `TRACE_WORKER_QUEUE` rather than a new dedicated queue

Material-trace jobs share the same workload profile as trace-lineage jobs (Oracle heavy query → parquet spool). The existing `trace-events` worker already handles this pattern. Adding a separate queue/worker would increase operational complexity for no benefit.

**Alternative considered:** Dedicated `material-trace` queue with its own worker — rejected because there is no isolation or scaling need that justifies an additional process.

### Decision 2: Define queue constant in `material_trace_service.py`, reference from route

Following the pattern in `reject_query_job_service.py` and `trace_lineage_job_service.py`, the constant `MATERIAL_TRACE_QUEUE` will be defined in the service module and imported by the route. This keeps the route thin (Rule #1.3) and the queue name co-located with the worker function it dispatches.

### Decision 3: Add queue to `rq_monitor_service.py` known-queues list

The RQ monitor service maintains a list of known queues for the admin dashboard. The `trace-events` queue is already listed, so no new entry is needed — but if a dedicated queue were used in the future, it would need to be added here.

## Risks / Trade-offs

**[Risk] Shared worker contention** → The `trace-events` worker is single-process. A large material-trace job could block trace-lineage jobs and vice versa. **Mitigation:** This is the existing trade-off for all jobs on this worker. Accepted for now; can be split later if contention is observed.

**[Risk] Orphaned jobs in `default` queue** → Jobs already stuck in the `default` queue from prior attempts will remain there. **Mitigation:** These jobs have a TTL and will expire from Redis. No manual cleanup required.
