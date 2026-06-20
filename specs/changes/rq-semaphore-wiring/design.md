# Design: rq-semaphore-wiring

## Summary
Bound Oracle-phase concurrency across the four heavy RQ workers by wiring the existing
cross-job `global_concurrency` semaphore (`acquire_heavy_query_slot` / `release_heavy_query_slot`,
`HEAVY_QUERY_MAX_CONCURRENT` default 3, Redis Lua-CAS, fail-open) around — and only around —
the Oracle fetch inside each `execute_*_job`. This closes the wiring gap recorded in
service-patterns.md §RQ Worker Concurrency Gate and realizes ADR 0011's decision that the
slot is acquired *inside the RQ worker around the Oracle fetch*, never at route/enqueue time.
Acquisition must be exception-safe (slot released on success and on failure) so a raising
Oracle phase or job timeout cannot leak a permit (AC-3, AC-4). No new env var, no job-output
or response-shape change (AC-7); flag-off paths stay byte-for-byte identical (AC-5).

## Affected Components
| component | file path(s) | nature of change |
|---|---|---|
| query-tool worker | `src/mes_dashboard/services/query_tool_service.py` (`execute_query_tool_job`, ~2783) | wrap the `result = get_*(...)` dispatch block (Oracle phase) in acquire/release |
| hold worker | `src/mes_dashboard/services/hold_query_job_service.py` (`execute_hold_history_query_job`, ~94) | wrap `execute_primary_query(...)` call in acquire/release |
| resource worker | `src/mes_dashboard/services/resource_query_job_service.py` (`execute_resource_history_query_job`, ~94) | wrap `execute_primary_query(...)` (base+OEE fan-out) in acquire/release |
| reject worker | `src/mes_dashboard/services/reject_query_job_service.py` (`execute_reject_query_job`, ~124) | **no acquire added** — already covered transitively (see D3) |
| semaphore (optional CM) | `src/mes_dashboard/core/global_concurrency.py` | optional: add a `contextmanager` helper so the documented `with` form is real (see D2) |
| pattern doc | `docs/architecture/service-patterns.md` §RQ Worker Concurrency Gate | stale claim "reject unwired" must be corrected (reject is wired at cache layer) |

## Key Decisions

- **D1 — Acquire scope = Oracle-phase only, not job-global.** The slot brackets just the Oracle
  fetch: for query-tool the `get_*(...)` dispatch (between pct=15 and pct=90 milestones); for
  hold/resource the `execute_primary_query(...)` call. Job setup, progress emits, query-id hashing,
  Redis result store, and `complete_job` stay outside. This conforms to ADR 0011 ("inside the RQ
  worker around the Oracle fetch") and AC-6 (acquire exactly once, only around the Oracle phase,
  context-managed). Job-global scope would hold the permit during non-Oracle work, shrinking
  effective Oracle headroom below 3 for no benefit.

- **D2 — Function returns `bool`, NOT a context manager.** `acquire_heavy_query_slot()` returns a
  bool (fail-open `True` when Redis is down) and is paired with `release_heavy_query_slot(owner)`.
  The `with acquire_heavy_query_slot():` form in service-patterns.md is currently aspirational and
  does not work as written. Two conforming options; **recommended: add a thin `@contextmanager`
  wrapper** in `global_concurrency.py` so AC-6's "context-managed" is literally satisfied and the
  doc becomes truthful. Minimal pattern (the existing idiom is also in `production_history_service.py:522`):
  ```
  owner = f"{job_type}:{job_id}"
  acquired = acquire_heavy_query_slot(owner)
  try:
      result = <oracle phase>
  finally:
      if acquired:
          release_heavy_query_slot(owner)
  ```
  A CM helper wraps exactly this try/finally and yields the `acquired` bool. `release` must be
  guarded by `acquired` so a fail-open path does not call release for a permit it never counted.

- **D3 — Multiple Oracle phases per job.**
  - query-tool: single phase. No re-acquire.
  - hold: `execute_primary_query` is the only billed phase; the later `ensure_canonical_spool` is a
    cheap Redis no-op in the normal case — do **not** bracket it (would be a second acquisition,
    violating AC-6's "exactly once"). If profiling later shows it issues real Oracle work, it is a
    separate change.
  - resource: `execute_primary_query` fans base+OEE out over `ThreadPoolExecutor(max_workers=2)` —
    that is **2 Oracle connections under 1 slot**, deliberately tolerated (worker launch sets
    `DB_POOL_SIZE=2`). The semaphore bounds *jobs*, not raw connections; DBA headroom is
    `HEAVY_QUERY_MAX_CONCURRENT × per-job parallelism` per ADR 0011 Consequences. Acquire still
    happens once, around the whole `execute_primary_query`. `ensure_canonical_spool` here may touch
    Oracle but is best-effort/non-fatal; keep it outside the slot to honor single-acquire.
  - reject: `execute_reject_query_job` calls `reject_dataset_cache.execute_primary_query`, which
    **already acquires/releases the slot internally** (cache lines 976/1231, owner `sync:<pid>:...`).
    Adding a job-level acquire would double-count one job as two slots → AC-1/AC-6 violation and
    artificially lowers cap. Decision: leave reject as-is; the change here is only to recognize and
    document it. (service-patterns.md must be corrected — it wrongly lists reject as unwired.)

- **D4 — `progress_callback` vs. blocking acquire.** query-tool/hold/resource workers emit only
  *coarse bracket milestones* via `update_job_progress` and pass **no** `progress_callback`; the
  Oracle call is opaque, so blocking on acquisition before it cannot stall any callback. The slot is
  acquired *after* the pct=15 "querying" emit and released before pct=90, so progress ordering is
  unchanged. Reject's per-chunk `progress_callback` lives inside the cache function that already
  owns its slot — unchanged. AC-5 (flag-off parity incl. `progress_callback` sequence) holds because
  the wrapper adds no progress emits and, when Redis is absent, fail-open returns immediately.

- **D5 — heavy_query_telemetry.py: not in scope for write.** Its counters track guard rejects,
  memory errors, spool hit/miss, and lock fail-modes — not slot acquire/release timing. Adding
  acquire-latency metrics would be a new contract surface beyond this change (AC-7 keeps scope to
  wiring). Slot wait/peak evidence for AC-1..AC-3 comes from `get_active_slot_count()` sampling in
  the stress harness, not telemetry counters. If observability is wanted later, prefer a dedicated
  `slot_wait`/`slot_peak` counter in a follow-up rather than overloading existing fields.

## Rejected Alternatives
- **Acquire at job-global scope (entire `execute_*_job`).** Holds the permit through progress emits,
  spool writes, and `complete_job`, reducing real Oracle parallelism below the intended 3 and
  coupling permit hold-time to Redis/result-store latency. Rejected per D1 / AC-6 and ADR 0011.
- **Per-worker (per-process) mutex instead of the shared global semaphore.** A local mutex bounds
  one worker process but cannot bound *cross-worker* Oracle concurrency — exactly the four-worker
  exhaustion ADR 0011 targets. It also can't fail-open coherently or share a cluster-wide cap.
  Rejected: only the Redis-backed cross-job semaphore satisfies AC-1.

## Migration / Rollback
Safe to deploy with existing `*_USE_RQ` flags untouched: wiring only adds an acquire/release around
an already-existing call; with a flag OFF the worker is not invoked, so behavior is identical (AC-5).
With Redis down, acquire fails open to `True` and runs unbounded exactly as today — no new failure
mode. No schema, env-var, or response change, so no data or contract migration. **Rollback** is a
pure code revert of the wrapper lines (and, if added, the CM helper); no state, key, or flag cleanup
is required — the semaphore key (`heavy_query_slots`) self-expires via its 600s TTL. Per
service-patterns.md checklist, real-Oracle load evidence (`peak_concurrent ≤ 3`, no leak, no
deadlock) is required in stress-soak-report.md before any new `*_USE_RQ=on` promotion.

## Open Risks
- service-patterns.md §RQ Worker Concurrency Gate states reject is unwired and shows a non-working
  `with acquire_heavy_query_slot():` form — both are wrong; doc-owner must correct alongside this change.
- Reject's slot owner is `sync:<pid>:<lock_owner>` (a pre-async naming relic) even when run in the
  RQ worker; harmless for counting but misleading in logs — note for a future cleanup, not this change.
- resource's 2-connection-per-slot fan-out means DBA headroom must be validated as
  `3 × 2 + overhead`; confirm against the worker `DB_POOL_SIZE`/`DB_MAX_OVERFLOW` launch settings
  before promotion (ADR 0011 Consequences).
