# Stress / Soak Report

Change: `add-uph-performance-page`. Required per `change-classification.md` Optional Artifacts
table ("new heavy Oracle worker on shared concurrency semaphore + large table with prior
timeouts warrants durable load/soak evidence") and gated explicitly by `ci-gates.md` Promotion
Policy step 2: **`stress-soak-report.md` sign-off is mandatory before
`mes-dashboard-uph-performance-worker.service` is first started in ANY environment.**

## Workload Model

`UphPerformanceJob(BaseChunkedDuckDBJob)` becomes a 4th named heavy consumer of the shared
global `heavy_query_slot` semaphore (`HEAVY_QUERY_MAX_CONCURRENT=3`, `core/global_concurrency.py`,
ADR-0011), alongside `eap_alarm`, `production_achievement`, and the other
`BaseChunkedDuckDBJob` subclasses (`downtime`, `material_trace`, `production_history`,
`reject_history`, `resource_history`) that already share the same cap. It queries
`DWH.EAP_EVENT ⋈ EAP_EVENT_DETAIL` (~12M rows/24h for GDBA alone), a table with a documented
history of >180s timeouts on unchunked 24h-window queries
(`docs/architecture/eap-event-uph-collection-investigation.md`) — mitigated by
`chunk_strategy=TIME` (≤6h windows, UPH-01) and `max_parallel=3` (unchanged concurrency knob,
per design.md non-goal).

Modeled workloads, all in `tests/stress/test_uph_performance_stress.py` unless noted:

| workload | shape | what it exercises |
|---|---|---|
| Burst | N=20 real `UphPerformanceJob.run()` calls, concurrent threads | slot acquire/release wiring, no leak, bounded peak concurrency |
| Mixed fault | N=20, every 5th `_fan_out_append` raises | slot released even when the Oracle fan-out fails; no deadlock |
| Cross-worker fairness | 10 UPH jobs + 10 generic sibling-domain stub jobs, interleaved thread starts | UPH does not monopolize or get starved of the shared CM vs. the other 6 consumer types |
| Fail-open | Redis unavailable | `acquire_heavy_query_slot` returns `True` near-instantly; `job.run()` still completes and writes a valid spool |
| Spool-key collision | N=5 threads, barrier-synchronized, IDENTICAL `(date_from, date_to)` → identical canonical spool key, real (small, stubbed-enrichment) chunk rows | concurrent identical-request thundering herd against `post_aggregate`'s direct-to-canonical-path `COPY ... TO` |
| Spool-key isolation | N=5 threads, DISTINCT date ranges | distinct canonical keys never cross-contaminate rows |
| Structural: no second slot acquisition | AST scan of `uph_performance_worker.py` | proves the worker source contains **zero** direct calls to `acquire_heavy_query_slot` / `release_heavy_query_slot` / `heavy_query_slot`, and does not import `global_concurrency` at module scope — the slot is acquired exactly once, inside the inherited `BaseChunkedDuckDBJob.run()` |
| Soak (folded) | `tests/integration/test_soak_workload.py` `_TRAFFIC_ENDPOINTS` rotation, 30-min default window | `POST /api/uph-performance/spool` added to the SAME rotation as the 8 other high-traffic endpoints (health, reject-history, hold-overview, query-tool, resource-history, hold-history, wip-detail, production-achievement); RSS / pool / DuckDB-temp / Redis-key-count / circuit-breaker / RQ-queue-depth six-property checks now also see UPH traffic mixed in with every other domain's traffic on the same 2-gunicorn-worker harness |
| Soak (folded) | `test_uph_performance_spool_ttl_cleanup_reclaims_namespace` (new, mirrors the `production_achievement` equivalent) | proves `cleanup_expired_spool()` reclaims both the parquet file and the Redis metadata pointer for the `uph_performance` namespace once TTL elapses — the new namespace was not accidentally left out of the shared, domain-agnostic reclaim mechanism |

**What this workload model explicitly does NOT include:** a real/sustained Oracle load run against
`DWH.EAP_EVENT`/`EAP_EVENT_DETAIL`. Per this session's established security boundary, live Oracle
access in this environment is reserved for the one-time, narrow-window, read-only exploratory
probe already run and recorded by backend-engineer (design.md §Pre-build exploratory probe,
UPH-03) — not for sustained/concurrent load testing. Every test above that exercises Oracle fetch
timing does so with `_fan_out_append` mocked to a no-op (or, for the two enrichment bridges in the
spool-collision tests, with `_safe_lot_product_df`/`_safe_workcenter_df` stubbed to empty frames)
— Oracle round-trip latency itself is never measured here. This mirrors exactly how
`production-achievement-async-spool`'s stress-soak pass was scoped (mock-based semaphore/spool
mechanics; the 5-concurrent live-server class exists in both suites but only runs against a
deployed instance via `STRESS_TEST_URL`, never in this sandbox).

## Duration

- Burst / mixed-fault / fairness / fail-open / spool-collision tests: sub-second to a few seconds
  each (thread-based, no real I/O wait beyond a 20ms simulated-Oracle sleep per slot acquisition).
- Structural AST-scan test: instantaneous (no execution, source inspection only).
- Soak (folded, local smoke mode): 300s (`SOAK_DURATION_SECONDS` default per
  `scripts/soak_local.sh`); CI nightly mode runs 1800s (`soak-tests.yml`). This change adds one
  new rotation entry to the existing shared soak test — it does not introduce a new soak duration
  tier of its own.
- Live-server 5-concurrent queue-saturation class: designed for the weekly/manual
  `stress-tests.yml` dispatch against a real deployed instance (`STRESS_TEST_URL`); in this
  sandbox it gracefully skips with "Server unreachable" (no live server available), consistent
  with every other domain's equivalent class in `test_async_job_stress.py` /
  `test_production_achievement_stress.py`.

## Metrics

Mock-based stress layer (thread-level, no live metrics endpoint involved):
- Slot enter/exit counts (must be exactly 1:1 per `job.run()` call — no leak).
- Peak concurrent slot holders (recorded via a monotonic-clock instrumented CM substituted for
  the real Redis-backed `heavy_query_slot`).
- Completion / fault counts (must sum to N; no hangs — all `.join(timeout=...)` calls succeed).
- Slot-entry-order type distribution (first-half-of-entries must contain both job types — no
  acquisition-order monopolization bias).
- Spool file validity: schema (`DESCRIBE SELECT * FROM read_parquet(...)` == the 13-column
  data-shape §3.29 schema_version-1 set) and row count, post-concurrent-write.

Soak layer (unchanged six-property checkers from `test_soak_workload.py`, now also fed
UPH traffic): `pool.checkout`/`checkin` slope + saturation, `duckdb.temp_bytes` boundedness,
`redis.key_count` convergence, `worker_rss` growth, `circuit_breaker` transition count, `rq`
per-queue pending-depth ratio. UPH-specific TTL reclaim: `cleanup_expired_spool()` stats
(`meta_deleted` count) plus direct filesystem/Redis-key existence checks.

## Thresholds

- Slot leak: `enters == exits`, always (hard fail on any mismatch).
- Peak concurrency: `peak <= N` (sanity bound; the *real* `HEAVY_QUERY_MAX_CONCURRENT=3` cap
  enforcement itself is Redis-Lua-CAS logic owned by `global_concurrency.py` and is NOT
  re-verified here — CI has no Redis; see `test_base_job_semaphore_stress.py`'s own note on this
  and `docs/architecture/base-job-semaphore-wiring-stress-soak-report.md` "Note on
  peak_concurrent").
- Fail-open acquire latency: `< 1.0s` (near-instant, no retry/backoff when Redis is down).
- `job.run()` completion with Redis down: `< 10.0s` (no material delay introduced by the
  fail-open path).
- Spool-collision safe-degradation invariants (not "zero errors" — see rationale in the test
  docstring, inherited from the pre-existing `production_achievement` finding): at least one
  writer succeeds; every error is the specific known IO/rename-race class; the surviving parquet
  has the correct schema.
- Structural: zero direct calls to `acquire_heavy_query_slot`/`release_heavy_query_slot`/
  `heavy_query_slot` in `uph_performance_worker.py`; zero direct `global_concurrency` imports.
- Soak six properties: unchanged existing thresholds (pool slope ±0.05/sample @ N≥20 samples,
  DuckDB temp bytes ≤ 3×Q1, Redis key-count drift ≤10% (or ≤3 keys at low absolute counts), RSS
  growth <15% head-median→tail-median, <3 circuit-breaker transitions, RQ queue tail ≤1.5×head) —
  this change does not introduce a new threshold, it adds UPH traffic into the existing evaluated
  window.
- TTL reclaim: `meta_deleted >= 1`; Redis metadata key absent after cleanup; parquet file absent
  after cleanup.

## Commands / Workflows

```bash
# Mock-based stress suite (this change's tests, excluding the live-server class)
conda run -n mes-dashboard python -m pytest tests/stress/test_uph_performance_stress.py \
  -v -m stress --run-stress -k "not QueueSaturation"

# Live-server class only (skips gracefully without STRESS_TEST_URL / a running instance)
conda run -n mes-dashboard python -m pytest \
  tests/stress/test_uph_performance_stress.py::TestUphPerformanceQueueSaturationLive \
  -v -m stress --run-stress

# Whole tests/stress/ tree (cross-check no regression in sibling suites)
conda run -n mes-dashboard python -m pytest tests/stress/ -m stress --run-stress \
  -k "not QueueSaturation and not Live"

# Folded soak: TTL-cleanup sub-test (fast, standalone, needs local Redis only)
conda run -n mes-dashboard python -m pytest \
  tests/integration/test_soak_workload.py::test_uph_performance_spool_ttl_cleanup_reclaims_namespace \
  -v --run-integration-real -m soak

# Folded soak: full 6-property workload run (local smoke, 300s; needs gunicorn_workers fixture)
SOAK_DURATION_SECONDS=300 SOAK_INTERVAL_SECONDS=30 \
  conda run -n mes-dashboard python -m pytest \
  tests/integration/test_soak_workload.py::test_soak_workload_six_property_regression \
  --run-integration-real -m soak -s
```

Per `ci-gates.md` Required Gates table: `stress-load` (weekly, activation-blocking) runs
`pytest tests/stress/ -m "stress or load"` (now includes this file); `soak` (weekly,
activation-blocking) runs `pytest tests/integration/test_soak_workload.py --run-integration-real
-m "soak"` (now includes both the extended `_TRAFFIC_ENDPOINTS` rotation and the new TTL test).
No new workflow file was required — both gates already existed and pick up the new file/entries
by directory/module scope.

## Results

All mock-based stress tests **PASS** in this environment:

```
tests/stress/test_uph_performance_stress.py::TestNoSecondSlotAcquisition::test_worker_source_never_calls_heavy_query_slot_directly PASSED
tests/stress/test_uph_performance_stress.py::TestNoSecondSlotAcquisition::test_semaphore_wiring_module_is_not_imported_for_manual_use PASSED
tests/stress/test_uph_performance_stress.py::TestSemaphoreWiringStress::test_burst_peak_bounded_no_leak PASSED
tests/stress/test_uph_performance_stress.py::TestMixedFaultNoDeadlock::test_burst_no_deadlock_with_mixed_success_failure PASSED
tests/stress/test_uph_performance_stress.py::TestCrossWorkerFairness::test_uph_and_sibling_jobs_interleave_no_monopolization PASSED
tests/stress/test_uph_performance_stress.py::TestFailOpenNoRedis::test_acquire_heavy_query_slot_fails_open_when_redis_down PASSED
tests/stress/test_uph_performance_stress.py::TestFailOpenNoRedis::test_job_run_completes_when_redis_down PASSED
tests/stress/test_uph_performance_stress.py::TestSpoolKeyCollision::test_identical_date_range_concurrent_jobs_no_spool_corruption PASSED
tests/stress/test_uph_performance_stress.py::TestSpoolKeyCollision::test_distinct_date_range_concurrent_jobs_stay_isolated PASSED
9 passed in 0.58s
```

`TestUphPerformanceQueueSaturationLive::test_uph_performance_5_concurrent` **SKIPPED** ("Server
unreachable") — expected in this sandbox (no live server/Oracle/Redis); this class is reserved for
the weekly/manual `stress-tests.yml` dispatch against a real deployed instance.

Folded-soak TTL-cleanup test **PASSES**:
```
tests/integration/test_soak_workload.py::test_uph_performance_spool_ttl_cleanup_reclaims_namespace PASSED
```

The full 30-minute (or 300s local-smoke) `test_soak_workload_six_property_regression` run was
**NOT executed as part of this pass** — it requires the `gunicorn_workers` fixture (real spawned
gunicorn processes) and is the pre-existing nightly/weekly gate owned by `ci-gates.md`'s `soak`
row; this change only adds the new `/api/uph-performance/spool` rotation entry and the TTL test
to that existing, separately-scheduled harness. It is not re-run ad hoc here because doing so
would not exercise anything Oracle-specific to this change beyond what the TTL test already
isolates (the traffic-thread hits the route with no auth session, so in this sandbox it would
only ever reach the 401/503 branches before touching Oracle — see the existing endpoints in the
same rotation for the identical caveat already documented in the module docstring's "Signal
strength: CI vs local" section).

Cross-check: the full `tests/stress/` tree (all sibling domains) was also run with this change's
suite included, to confirm no regression to any existing stress test from extending the shared
soak/stress infrastructure.

## Failure Triage

No failures observed in this pass. If a future run of this suite fails:

- **Slot leak (`enters != exits`)**: check whether a code change to `uph_performance_worker.py`
  introduced an exception path in `pre_query`/`post_aggregate` that escapes
  `BaseChunkedDuckDBJob.run()`'s `finally` block incorrectly, or whether the worker started
  manually acquiring/releasing `heavy_query_slot` (re-run `TestNoSecondSlotAcquisition` first —
  it will catch a re-acquisition regression structurally, before the leak count even needs
  inspecting).
- **Cross-worker fairness first-half-entry-types assertion fails**: this indicates an
  acquisition-order bias was introduced into the shared CM itself (a change to
  `global_concurrency.py`, not to this worker) — escalate as a cross-cutting regression, not a
  UPH-specific one.
- **Spool-collision test schema mismatch**: check `_SCHEMA_VERSION` in
  `uph_performance_cache.py` was bumped consistently with any parquet column change in
  `uph_performance_worker.py`'s `_build_final_select_sql` (data-shape §3.29 breaking-change
  surface) — a mismatch here usually means one was edited without the other.
  `rm -f tmp/query_spool/uph_performance/*.parquet` is the documented rollback if this happens in
  a running environment.
- **TTL-cleanup test failure**: check `spool_routes._ALLOWED_NAMESPACES` still includes
  `uph_performance` and that `cleanup_expired_spool()` was not given a domain-specific exclusion
  list that accidentally omits the new namespace.
- **Folded `_TRAFFIC_ENDPOINTS` soak entry causing a NEW six-property regression** (pool/DuckDB/
  Redis/RSS/circuit-breaker/RQ): bisect by temporarily commenting out just the new
  `/api/uph-performance/spool` rotation entry and re-running — if the regression disappears, the
  worker (or its route) is leaking a resource under repeated invocation that the mock-based stress
  suite above cannot see (real DuckDB/Redis/RQ activity only happens in the `gunicorn_workers`
  harness, not in the thread-only mock tests).

## Data-Availability Probe — RESOLVED (2026-07-13, post-implementation)

The other residual risk this change originally carried — whether `BondUPH` (GDBA) and `fHCM_UPH`
(GWBA) actually return non-empty data, given the 2026-07-08 investigation's finding of zero GWBA
UPH signal under the pre-reconfiguration parameter name — has been **confirmed resolved**, not
merely accepted as open risk. A <=6h read-only probe run directly against the real Oracle DWH
(explicit user authorization, 2026-07-13) found:

| family | parameter | distinct equipment | events (6h) | non-null values | sample range |
|---|---|---:|---:|---:|---|
| GDBA | BondUPH | 118 | 617 | 617 (100%) | 9581–12157 |
| GWBA | fHCM_UPH | 46 | 259 | 259 (100%) | 7750.36–21752.30 |

Both parameters are actively emitting data with 100% non-null values in the sampled window — this
directly reverses the prior investigation's zero-GWBA-signal finding, consistent with the user's
account that `fHCM_UPH` reporting on GWBA was configured recently. See
`agent-log/backend-engineer.yml`'s `oracle-probe` block for the full detail. This was a
single-point-in-time sample (coverage could still vary by shift), and the original investigation's
value-scale ambiguity (raw vs. implicit x100) remains unresolved but is moot for this change —
UPH-04 already mandates raw-value display regardless of the true physical scale.

## Residual Risk (carried forward, not closed by this change)

**Shared 3-slot `heavy_query_slot` semaphore now has a 4th real consumer under production
traffic, and the combined production load across all consumers sharing that cap has never been
tested against real Oracle.** This is a **pre-existing, cross-cutting gap**, not something
introduced or closeable by `add-uph-performance-page`:

- `design.md`'s own Open Risks section flags this explicitly as "monitoring, not a fix in this
  change" — concurrency-knob tuning (`HEAVY_QUERY_MAX_CONCURRENT`, `max_parallel`, RQ worker
  process count) is an explicit non-goal of this change (change-request.md Non-goals;
  implementation-plan.md Out of Scope).
- The same gap already existed before this change across the other consumers sharing the cap
  (`eap_alarm`, `production_achievement`, `downtime`, `material_trace`, `production_history`,
  `reject_history`, `resource_history`) — every one of those changes' own stress-soak passes was
  similarly scoped to mock-based semaphore/spool mechanics plus a live-server class that only runs
  when a deployed instance + `STRESS_TEST_URL` are available (per ADR-0011 and this repo's prior
  stress-soak-report precedent for `rq-semaphore-wiring` / `production-achievement-async-spool`).
  Adding UPH-Performance does not create a NEW class of risk; it adds one more named participant
  to an already-open, already-flagged shared-resource question.
- What COULD be verified in this environment (mock-based semaphore wiring, no-leak, no-deadlock,
  fairness-vs-stubs, fail-open, spool-key collision/isolation, folded soak TTL reclaim) all
  passed.
- What could NOT be verified in this environment, and remains open: real Oracle round-trip timing
  under genuine cross-domain concurrent contention (e.g. an EAP-ALARM burst and a UPH-Performance
  burst genuinely overlapping against production Oracle at the same time), and whether the ≤6h
  chunk cap's previously-measured 2–12s runtime (docs/architecture/
  eap-event-uph-collection-investigation.md) holds up when 3 of the 3 available slots are
  occupied by OTHER domains' queries simultaneously, forcing UPH-Performance chunks to queue
  behind them. `HEAVY_QUERY_MAX_CONCURRENT=3` is a hard cap, not a priority queue — under
  sustained multi-domain load, a UPH-Performance job could in principle wait an unbounded amount
  of time for a slot before its Oracle fetch even starts. This is not something the ≤6h
  chunk-window mitigation (which only bounds the *duration* of a single chunk once it IS running)
  can address.
- Live Oracle access in this environment is reserved for the one-time, narrow-window read-only
  probe already completed (design.md §Pre-build exploratory probe) — sustained/concurrent
  real-Oracle load testing requires explicit user authorization outside this agent's task scope,
  consistent with this session's established security boundary.

## Sign-off Recommendation

**Approved to start `mes-dashboard-uph-performance-worker.service`, conditional on the residual
risk above being accepted as a known, pre-existing, cross-cutting limitation** (not a defect
introduced by this change) — consistent with how every other `BaseChunkedDuckDBJob` sibling
worker sharing the same semaphore was activated:

1. All structural/mechanical semaphore-safety properties this stress suite CAN verify without a
   live Oracle load — no leak, no deadlock, no re-acquisition, no starvation vs. mocked sibling
   traffic, fail-open correctness, spool-key collision safe-degradation, and namespace TTL
   reclaim participation — pass.
2. The change's own mitigations for the documented >180s timeout history (≤6h `TIME` chunking,
   exact-match `PARAMETER_NAME` predicate rather than a blanket `IN`-list per ADR-0017, unchanged
   `max_parallel=3`) are structurally in place and unit-tested elsewhere
   (`tests/test_uph_performance_sql_builder.py`), and were spot-checked against real Oracle only
   via the narrow, one-time, read-only probe already completed by backend-engineer — not via
   sustained load, which this pass does not perform.
3. The rollback path is trivial and non-destructive if production contention turns out worse than
   expected: `UPH_PERFORMANCE_USE_UNIFIED_JOB=off` (pure kill switch, spool-miss → 503, no legacy
   path to corrupt) and/or `rm -f tmp/query_spool/uph_performance/*.parquet` — no other feature
   reads this namespace, so removal cannot orphan or corrupt shared state (design.md
   §Migration/Rollback).
4. **Recommendation to the user/operator, not a blocking condition of this sign-off:** after
   `mes-dashboard-uph-performance-worker.service` is started, monitor `rq_monitor_service` / Admin
   Dashboard Worker Status (ci-gates.md Promotion Policy step 4) specifically for
   `heavy_query_slot` queue-wait time and peak-concurrent-consumer counts across ALL 7+ domains
   for at least one full production day before considering the shared-semaphore question closed.
   If queue-wait times or Oracle-timeout rates measurably worsen after this worker starts, that is
   the trigger for the separate, out-of-scope concurrency-knob-uplift architecture change already
   flagged in design.md and this change's Non-goals — not a reason to roll back UPH-Performance
   itself, since the underlying contention risk was already latent across the existing 6
   consumers before this change added a 7th.
