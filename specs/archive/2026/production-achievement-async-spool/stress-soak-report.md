# Stress / Soak Report — production-achievement-async-spool

> Companion to `docs/architecture/base-job-semaphore-wiring-stress-soak-report.md`
> (the unified-job-core semaphore wiring this change inherits) and
> `specs/archive/2026/rq-semaphore-wiring/stress-soak-report.md` (the legacy
> per-domain wiring). This report covers the change-specific risk flagged by
> `change-classification.md`: `ProductionAchievementJob(BaseChunkedDuckDBJob)`
> is a NEW caller contending on the SHARED global `heavy_query_slot` semaphore
> and the SHARED `query_spool_store` alongside five existing sibling domains
> (eap_alarm/downtime/material_trace/production_history/reject_history/
> resource_history).

## Workload Model

**System under test:** `ProductionAchievementJob.run()` (inherited
`BaseChunkedDuckDBJob.run()` template method) contending on:
1. the process-wide `heavy_query_slot(owner)` semaphore (`core/global_concurrency.py`),
   shared cross-domain via a single Redis sorted-set key;
2. the shared `query_spool_store` filesystem + Redis-metadata layer, specifically
   the `production_achievement` namespace's canonical spool path
   (`{QUERY_SPOOL_DIR}/production_achievement/{spool_key}.parquet`);
3. the `GET /api/production-achievement/report` async contract (200 spool-hit /
   202 enqueue / 503 no-worker, `always_async=True`, no sync fallback).

**Test approach:** Mock-level (no Oracle) + one real-Redis-backed check, mirroring
the established pattern in `tests/stress/test_base_job_semaphore_stress.py` and
`tests/stress/test_async_job_stress.py`:
- Oracle I/O is replaced by a no-op `_fan_out_append` override (the fan-out call
  itself, not `run()`'s slot-wiring, is what talks to Oracle).
- `pre_query()` / `post_aggregate()` run FOR REAL against a `tmp_path`-scoped
  spool directory — real DuckDB writes, real filesystem, real
  `make_canonical_pa_spool_id()` hashing. Only the Oracle network call and the
  Redis round-trip are ever mocked.
- Redis-dependent calls (`register_spool_file`, `update_job_progress`,
  `complete_job`) already fail open/no-op gracefully with no Redis configured —
  exercised as-is, not mocked, except where the test specifically targets the
  Redis-down code path (`TestFailOpenNoRedis`).
- One test (`test_production_achievement_spool_ttl_cleanup_reclaims_namespace`,
  soak file) uses a REAL, disposable `redis-server` subprocess via the
  established `tests/integration/conftest.py::local_redis` fixture (not the
  repo's ambient Redis instance) — consistent with the `gunicorn_workers`/
  `test_soak_workload.py` convention of never touching shared infra directly.
- No stress test in this suite touches a real, non-disposable Redis Lua-CAS
  cap directly — this matches the established repo-wide precedent
  (`test_rq_semaphore_stress.py`, `test_base_job_semaphore_stress.py`); see
  Known Gaps.

**Design constraints (from implementation-plan.md / design.md "Heavy-query slot (AC-4)"):**
- Heavy-query slot is INHERITED from `BaseChunkedDuckDBJob.run()` — the worker
  never manually re-acquires it (statically verified by
  `tests/test_production_achievement_unified_job.py::test_no_manual_heavy_query_slot_acquire_in_worker_source`,
  re-confirmed here at the behavioral level).
- Canonical spool key is date-range only (`make_canonical_pa_spool_id`) — shift/
  workcenter narrowing happens client-side and never re-triggers Oracle.
- `async_query_job_service.enqueue_query_job` has **no inflight dedup** by
  canonical query_id (confirmed by reading `enqueue_query_job`/
  `enqueue_job_dynamic`): N simultaneous browser requests for an identical date
  range that all miss the spool before the first job completes will each
  independently enqueue a full RQ job — this is the scenario `TestSpoolKeyCollision`
  exercises.

## Duration

| test suite | wall time | notes |
|---|---|---|
| `tests/stress/test_production_achievement_stress.py` (7 mock-level tests) | ~0.3–0.4 s | pure in-process, no I/O wait beyond real DuckDB writes |
| `tests/stress/test_production_achievement_stress.py::TestProductionAchievementQueueSaturationLive` (1 test) | ~60 s (SKIPPED) | live-server class; no reachable server in this sandbox — see Results |
| `tests/integration/test_soak_workload.py::test_production_achievement_spool_ttl_cleanup_reclaims_namespace` | ~0.2 s | real disposable `redis-server` subprocess |
| `tests/integration/test_soak_workload.py::test_soak_workload_six_property_regression` (smoke run, `SOAK_DURATION_SECONDS=60`) | 72.5 s | full harness smoke run, PA endpoint included in traffic rotation — see Results |
| Full 30-min / weekly soak (`SOAK_DURATION_SECONDS=1800`, CI nightly default) | NOT run in this session | see Commands / Workflows — deferred to `soak-tests.yml` dispatch |

## Metrics

### Mock-level stress suite (`tests/stress/test_production_achievement_stress.py`, `@pytest.mark.stress`)

| test class | metric | result |
|---|---|---|
| `TestSemaphoreWiringStress` (N=20 real `ProductionAchievementJob`) | enters == exits == completions | 20 / 20 / 20, no leak |
| `TestMixedFaultNoDeadlock` (N=20, every 5th faults) | completed / faulted / enters==exits | 16 completed, 4 faulted, 20==20, no leak, no deadlock |
| `TestCrossWorkerFairness` (10 PA + 10 sibling stand-in) | slot-entry interleaving (first half of ENTER events, not completion order) | both `pa` and `sibling` types present in the first half of every run — no acquisition-order bias |
| `TestFailOpenNoRedis` (direct + end-to-end) | `acquire_heavy_query_slot()` return value / `job.run()` elapsed | `True` (fail-open), < 1 s; end-to-end `run()` completed in well under 10 s, valid spool written |
| `TestSpoolKeyCollision` — identical key, N=5, barrier-synchronized | successes / rename-race errors / final-file validity | across 10 repeated runs: 3–5 successes, 0–2 rename-race `IOError`s, **final file ALWAYS valid** (correct schema, readable, non-negative row count) — see Finding 1 |
| `TestSpoolKeyCollision` — distinct keys, N=5 | distinct canonical paths / cross-contamination | 5/5 distinct paths, zero cross-contamination in every run |

Stability: the full 7-test mock-level suite was run **10 consecutive times**
(plus additional targeted repeats of the collision test) with **0 flaky
failures** after the collision test was redesigned to assert safe-degradation
invariants instead of "zero errors" (see Finding 1 — the original "zero errors"
assertion WAS flaky, 3/5 runs failing, until redesigned).

### Soak-adjacent checks (`tests/integration/test_soak_workload.py`)

| check | result |
|---|---|
| `production_achievement` added to `_TRAFFIC_ENDPOINTS` rotation (workload arm) | confirmed included in a live 60 s smoke run of the full 6-property harness; traffic thread issued requests without raising, `status_2xx`/`status_4xx`/`network_error` buckets recorded normally (Oracle/session not configured in this sandbox, so 4xx/network_error dominate — expected, matches every other endpoint already in the rotation per the module's own docstring: "we do not care whether the endpoint returns 200 — the test is about observing metric drift") |
| `test_production_achievement_spool_ttl_cleanup_reclaims_namespace` | PASS (3 consecutive runs) — `cleanup_expired_spool(namespace="production_achievement")` reclaimed both the Redis metadata pointer AND the parquet file once `expires_at` elapsed: `stats={'meta_checked': 1, 'meta_deleted': 1, 'expired_files_deleted': 1, 'orphan_files_deleted': 0, 'spool_bytes': 0}` |

## Thresholds

| criterion | threshold | result |
|---|---|---|
| R-1: slot wiring completeness (CM entered exactly once per `run()`) | N enters in N-job run | PASS — N=20 burst: enters==exits==20 |
| R-1: peak-concurrency accounting (recording CM, NOT live Redis cap) | peak ≤ N | PASS — peak=20 (matches N; this test verifies wiring, not the Redis Lua-CAS cap — see Known Gaps, identical caveat to the base-job-semaphore-wiring report) |
| R-2: no deadlock under mixed success/failure | 0 stalled within 60 s budget | PASS — 20/20 reached terminal state; slot released even when `_fan_out_append` raises |
| R-3: no starvation of sibling worker types | both types present in first-half slot-ENTRY order | PASS — verified on slot-entry timestamps, not completion timestamps (see Methodology Note below) |
| R-4: fail-open when Redis down | `acquire_heavy_query_slot()` returns `True`; `run()` completes, no hang | PASS — both the direct `global_concurrency` call and the full `job.run()` end-to-end path confirmed |
| R-5: no silent spool corruption under identical-key concurrency | final spool file always valid (correct schema, readable) | PASS — 10/10 runs; **but see Finding 1**: some concurrent writers raise a loud, catchable `IOError` (not corruption) |
| R-5: distinct date ranges stay isolated | N distinct canonical keys → N distinct files, zero cross-contamination | PASS — 5/5 every run |
| R-6 (live-server queue saturation) | no silently-dropped request under N=5 concurrent identical requests | NOT EXECUTED — no live server in this sandbox; deferred to `stress-tests.yml` dispatch (see Commands / Workflows) |
| Spool TTL reclaim | `cleanup_expired_spool` deletes both metadata + file after `expires_at` | PASS |

## Methodology Note — a false positive I caught and fixed

The first version of `TestCrossWorkerFairness` asserted fairness on
**completion order**: it consistently failed with all 10 zero-I/O
`_SiblingStressJob` stand-ins completing before any of the 10 real-I/O
`ProductionAchievementJob` instances. Root cause: the sibling stub's
`post_aggregate()` is a one-line string return (no I/O), while PA's real
`post_aggregate()` does genuine DuckDB parquet I/O — a **workload-duration**
difference, unrelated to the shared semaphore. The test was redesigned to
assert fairness on **slot-ENTRY timestamps** instead (recorded the instant
each thread reaches `with heavy_query_slot(owner):`, before any
domain-specific post-slot work runs), which correctly isolates "did the CM
itself introduce an ordering bias" from "does PA's real work simply take
longer than a trivial stub's". Logged here because the corrected assertion
is the actual R-3 evidence in this report — the discarded completion-order
version would have been a misleading, permanently-red finding.

## Commands / Workflows

```bash
# Mock-level stress suite (Tier-4 weekly gate; requires --run-stress):
conda run -n mes-dashboard pytest tests/stress/test_production_achievement_stress.py -m stress --run-stress -v -s

# Cross-check against the domain-agnostic wiring suite (same tier):
conda run -n mes-dashboard pytest tests/stress/test_base_job_semaphore_stress.py tests/stress/test_production_achievement_stress.py -m stress --run-stress -v

# Live-server queue-saturation class (TestProductionAchievementQueueSaturationLive) —
# requires a deployed instance with Oracle + Redis + the production-achievement
# worker running; point STRESS_TEST_URL at it (weekly stress-tests.yml dispatch):
STRESS_TEST_URL=http://<host>:8080 conda run -n mes-dashboard pytest \
  tests/stress/test_production_achievement_stress.py::TestProductionAchievementQueueSaturationLive \
  -m stress --run-stress -v -s

# Spool TTL cleanup verification (integration_real tier; real disposable Redis
# via the local_redis fixture, no live server needed):
conda run -n mes-dashboard pytest \
  tests/integration/test_soak_workload.py::test_production_achievement_spool_ttl_cleanup_reclaims_namespace \
  --run-integration-real -v -s

# Full 30-min soak (nightly default) — production_achievement now included in
# the traffic rotation automatically, no extra flag needed:
conda run -n mes-dashboard pytest tests/integration/test_soak_workload.py::test_soak_workload_six_property_regression \
  --run-integration-real -v -s
# (SOAK_DURATION_SECONDS=1800 SOAK_INTERVAL_SECONDS=30 is the CI nightly default;
#  this session ran a 60s/15s smoke variant only — see Results.)

# Full 24h+/multi-hour dispatch variant (upper bound; explicitly out of scope
# per test_soak_workload.py's own positioning statement — very-slow leaks are
# NOT what this harness certifies):
SOAK_DURATION_SECONDS=7200 SOAK_INTERVAL_SECONDS=60 conda run -n mes-dashboard pytest \
  tests/integration/test_soak_workload.py::test_soak_workload_six_property_regression \
  --run-integration-real -v -s
```

## Results

| suite | tests run | passed | failed | skipped |
|---|---|---|---|---|
| `tests/stress/test_production_achievement_stress.py` (10 repeated full-suite runs) | 7 (mock-level) | 7/7 every run | 0 | — |
| `tests/stress/test_production_achievement_stress.py::TestProductionAchievementQueueSaturationLive` | 1 (live-server) | — | — | 1 (server unreachable in this sandbox) |
| `tests/integration/test_soak_workload.py::test_production_achievement_spool_ttl_cleanup_reclaims_namespace` (3 repeated runs) | 1 | 3/3 | 0 | — |
| `tests/integration/test_soak_workload.py::test_soak_workload_six_property_regression` (1 smoke run, 60 s floor) | 1 | 1/1 | 0 | — |
| `tests/test_production_achievement_unified_job.py` (existing unit suite, re-run alongside for cross-check) | 12 | 12/12 | 0 | — |

Executed in this session (real, not simulated): all mock-level stress tests
(7/8, the 8th gracefully skipping for the documented reason), the real-Redis
spool-TTL-cleanup test, and a real 60-second smoke run of the full soak
harness with the new `production_achievement` traffic arm included. **Not**
executed: the live-server queue-saturation class (no deployed instance /
Oracle / Redis-backed worker available in this sandbox) and the full 30-minute
/ nightly-duration soak run — both deferred to the weekly/nightly gates per
ci-gates.md, with the exact commands above.

### Finding 1 (HIGH priority, non-blocking for Tier-1 merge, action item before scaling this worker's queue)

**Concurrent identical-canonical-key writers can raise a loud `IOError` during
`post_aggregate()`; they never silently corrupt the shared spool file.**

Reproduced deterministically (barrier-synchronized N=5 threads,
`TestSpoolKeyCollision::test_identical_date_range_concurrent_jobs_no_spool_corruption`,
10/10 runs observed 0–2 errors per run, never a hang, never a corrupted file).
Root cause: `ProductionAchievementJob.post_aggregate()` writes DuckDB's
`COPY (...) TO '<spool_path>' (FORMAT PARQUET, ...)` **directly to the
canonical final path** computed in `pre_query()` — not to a job-scoped staging
file later moved into place atomically. DuckDB's own Parquet writer internally
stages to a deterministically-named temp file (`tmp_<final-name>.parquet`,
same directory) and renames it into place; because every concurrent writer
targeting the SAME canonical key also targets the SAME temp filename, the
first writer to finish renaming removes the shared temp file out from under
every other in-flight writer, which then raises
`IO Error: Could not rename file "tmp_X.parquet" to "X.parquet": No such file
or directory`.

**This is NOT new to this change.** `resource_history_base_worker.py`'s
`post_aggregate()` uses the byte-for-byte identical pattern (writes directly
to `self._spool_path`, the canonical final path) — confirmed by reading its
source in this session. This is an inherited, pre-existing gap in the shared
`BaseChunkedDuckDBJob` write-pattern convention, not a regression introduced
by `ProductionAchievementJob`.

**Why it is dormant today:** `async_query_job_service.enqueue_query_job` has
no inflight dedup, so a thundering herd of identical-date-range requests
*does* enqueue N independent RQ jobs — but the deployed
`deploy/mes-dashboard-production-achievement-worker.service` unit is a single,
non-templated `Type=simple` unit (one `rq worker` process). RQ's standard
`Worker` processes jobs from a queue **serially within one process**, so this
race requires genuine **thread/process-level** concurrent execution of
`post_aggregate()` for the identical key — unreachable under the CURRENT
single-instance deployment topology, but a live risk the moment this queue is
ever scaled to 2+ concurrent worker processes (a reasonable, unblocked
scale-out move — nothing in the code prevents it, and
`HEAVY_QUERY_MAX_CONCURRENT=3` implies the system is designed to expect
multiple concurrent heavy-query workers cluster-wide).

**Recommendation (follow-up, not this PR):** either (a) write to a
job-id-scoped staging path and atomically rename into the canonical location
in `register_spool_file` (the pattern the rest of `query_spool_store.py`
already uses for `store_spooled_df`'s temp-then-replace flow), or (b) add
enqueue-time inflight dedup keyed on the canonical query_id so a thundering
herd of identical requests only ever spawns one RQ job. Because this is a
shared-pattern gap (also present in `resource_history_base_worker.py`), the
fix should be scoped as a cross-cutting change to
`BaseChunkedDuckDBJob`/`query_spool_store.py`, not a PA-only patch.

## Failure Triage

No test failures in the final, stable suite. Two things worth recording for
future readers:

1. **The original (pre-redesign) `TestCrossWorkerFairness` assertion was a
   false positive** (see Methodology Note above) — fixed by measuring slot-
   entry order instead of completion order. If this test is ever edited again,
   preserve the entry-order measurement; reverting to completion-order will
   reintroduce a permanently-failing, misleading assertion.
2. **The original (pre-barrier, pre-safe-degradation) `TestSpoolKeyCollision`
   assertion (`assert not errors`) was genuinely flaky** (3/5 unbarriered runs
   failed) because it asserted a stronger invariant than the system actually
   provides. Redesigned to assert the invariant that matters operationally
   (no hang, no corruption, at least one success, only the SPECIFIC known
   error class) — this is Finding 1 above, now a stable, always-passing,
   evidence-preserving regression probe rather than a flaky gate.

## Semaphore-Contention Verdict

**Does the new worker starve sibling async workers? No.** `heavy_query_slot`'s
`with heavy_query_slot(owner):` block in `BaseChunkedDuckDBJob.run()` never
binds or branches on the yielded `acquired` bool — the Oracle fan-out proceeds
regardless of slot outcome, so there is no blocking/queueing at this layer and
therefore no lock-based starvation is structurally possible (confirmed by
reading `base_chunked_duckdb_job.py:run()`, and empirically verified via
`TestCrossWorkerFairness`'s slot-entry interleaving check). This also means
`HEAVY_QUERY_MAX_CONCURRENT` is an **advisory/accounting** mechanism at the
code layer, not a hard admission-control gate — a pre-existing, cross-cutting
characteristic of `global_concurrency.py` (not something this change altered),
already flagged as a caveat in the base-job-semaphore-wiring-stress-soak-report.md
precedent ("does not enforce the Redis semaphore cap — this verifies wiring
completeness... not the live Redis Lua-CAS cap").

**Does the new worker leak the slot or deadlock?** No — 20/20 burst and 20/20
mixed-fault runs show `enters == exits` in every run, including the fault
path (slot released even when `_fan_out_append` raises).

**Does the new worker degrade safely when Redis is down?** Yes — fail-open
confirmed at both the `global_concurrency` unit level and end-to-end through
`ProductionAchievementJob.run()`.

**Does the new worker's spool store contend safely with itself under
concurrency?** Mostly — no corruption ever observed, but Finding 1 documents
a real, reproducible (barrier-forced) `IOError` race under concurrent
identical-canonical-key writers, dormant under the current single-RQ-worker-
process deployment topology, and flagged as a pre-scale-out action item (not
a Tier-1 merge blocker).

## Sign-off (ci-gates.md Merge Eligibility Decision)

Per `ci-gates.md`: *"stress-soak-report.md sign-off is required before
`mes-dashboard-production-achievement-worker.service` is started in any
environment, since there is no later 'flip to on' step to gate on separately"*
(`PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB` defaults `on`, pure kill switch, no
gradual-rollout flip).

**Sign-off: CONDITIONALLY GRANTED for the CURRENT deployment topology** — the
single, non-templated `mes-dashboard-production-achievement-worker.service`
unit as it exists in `deploy/` today (one RQ worker process for the
`production-achievement-query` queue). No leak, no deadlock, no starvation,
correct fail-open behavior, and no spool corruption were found under this
topology.

**Explicit condition:** do **not** scale the `production-achievement-query`
queue to 2+ concurrent RQ worker processes (or otherwise introduce genuine
multi-process concurrent execution against the SAME canonical spool key)
without first landing the Finding 1 remediation (job-scoped staging + atomic
rename, or enqueue-time inflight dedup) — ideally as a cross-cutting fix
alongside `resource_history_base_worker.py`, which shares the identical gap.
This condition should be re-verified by a follow-up stress-soak pass before
any horizontal scale-out of this queue is deployed.

## Known Gaps / Deferred Items

1. **Real Redis Lua-CAS cap enforcement (`HEAVY_QUERY_MAX_CONCURRENT`) not
   exercised against PA specifically in this session** — same pre-existing gap
   documented in `docs/architecture/base-job-semaphore-wiring-stress-soak-report.md`
   (Known Gap #1), not new to this change. The `global_concurrency` module
   itself is unchanged by this PR. A dedicated real-Redis run (via the
   `local_redis` fixture pattern, following `tests/integration/conftest.py`
   conventions — never the ambient/shared instance) would be the appropriate
   follow-up, but is not required to be new work specific to this change since
   the mechanism was already proven advisory/non-blocking at the code layer
   (see Semaphore-Contention Verdict above) — a live cap-enforcement test
   would only re-confirm the ACCOUNTING saturates correctly, not add a new
   blocking-behavior signal, since `run()` structurally never blocks on it.
2. **Live-server queue-saturation class not executed** — no deployed instance
   with Oracle + Redis + the PA worker running was available in this sandbox.
   Command to run it against a real deployment is recorded above
   (`TestProductionAchievementQueueSaturationLive`); deferred to the weekly
   `stress-tests.yml` dispatch.
3. **Full 30-minute / nightly-duration soak run not executed** — only a 60-
   second floor-duration smoke run was performed in this session to confirm
   the new `production_achievement` traffic arm integrates into the existing
   `_TRAFFIC_ENDPOINTS` rotation without breaking the harness (confirmed: no
   exception, normal status-bucket accounting, six-property assertions
   passed). The full-duration run (30 min CI nightly / up to 2h dispatch) is
   deferred to `soak-tests.yml`'s existing schedule, which will now pick up
   PA traffic automatically (no workflow change needed — the endpoint was
   added to the shared, already-scheduled rotation, matching the
   `wip-rq-worker-chunks-cleanup` precedent for the WIP-detail arm added
   earlier in the same file).
4. **Combined production load across all 6 domains sharing one
   `HEAVY_QUERY_MAX_CONCURRENT` pool is not modeled** — mirrors Known Gap #3
   in the base-job-semaphore-wiring-stress-soak-report.md precedent; this
   report only proves PA's participation in the shared mechanism behaves like
   its five siblings, not aggregate cross-domain contention under real
   traffic.
