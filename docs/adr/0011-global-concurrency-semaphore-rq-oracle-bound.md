# ADR 0011: global_concurrency semaphore re-scoped to bound RQ Oracle concurrency

## Status
proposed

## Context
`core/global_concurrency.py` (`HEAVY_QUERY_MAX_CONCURRENT`, default 3; Redis
sorted-set + Lua CAS; fail-open) was introduced to cap concurrent *synchronous*
heavy queries so Path C did not exhaust gunicorn workers. The
query-dataflow-unification plan (P4+P5, change `query-path-c-elimination-cleanup`)
eliminates Path C: oversized `query_tool` and `wip` queries now enqueue to RQ
instead of blocking workers. With no synchronous heavy path left, the semaphore's
original purpose no longer exists, but the mechanism is still needed — now to
bound how many RQ heavy jobs hit Oracle at once so the connection pool and DB
session quota are not exhausted (blueprint §4.2 / §5.2).

## Decision
Re-document the semaphore's role from "protect the synchronous request path" to
"limit the number of RQ heavy jobs concurrently querying Oracle (cross-job
bound)". The slot is acquired **inside the RQ worker** around the Oracle fetch,
not at route/enqueue time. Runtime mechanics — Lua CAS, fail-open on Redis
outage, 600s TTL, `HEAVY_QUERY_MAX_CONCURRENT` default 3 — are unchanged. The
contract (business-rules.md, env-contract.md) is updated to the new semantics.

## Consequences
- The semaphore no longer gates the request thread; a blocked slot causes RQ jobs
  to queue/degrade, never a stalled gunicorn worker.
- Oracle session quota planning shifts to: `HEAVY_QUERY_MAX_CONCURRENT` × per-job
  chunk parallelism + headroom (must be confirmed with DBA; see blueprint §5.2).
- Reversing this (re-pointing the semaphore at a synchronous path) would silently
  re-introduce worker-blocking Path C — hence this ADR fixes the intent.
- No code-behavior change ships in this step beyond call-site placement; stress
  evidence (no worker starvation, bounded Oracle concurrency) is required before
  acceptance.
