# Stress / Soak Report

**Change:** wip-rq-worker-chunks-cleanup
**Date:** 2026-06-20
**Engineer:** stress-soak-engineer

---

## Workload Model

**Domain:** WIP detail async query — `execute_wip_detail_job` (new RQ worker, registered as `"wip-detail"`)

**Slot model:** One `heavy_query_slot` per job, wrapping the Oracle phase only (progress milestones 15→90). No fan-out, no ThreadPoolExecutor doubling — single primary query per job (design decision D2). Contrast with resource worker which acquires 2 connections per job slot; WIP detail acquires exactly ONE Oracle connection per slot.

**Concurrency cap:** `HEAVY_QUERY_MAX_CONCURRENT = 3` (env default, Redis-backed sorted-set semaphore).

**Burst test size:** N=20 concurrent simulated jobs (matches canonical semaphore stress suite in `test_rq_semaphore_stress.py`).

**Simulated I/O duration:** 20ms sleep inside recording CM — sufficient to produce genuine time-window overlap across all 20 threads and prove burst behavior.

---

## Duration

| Mode | Duration | Trigger |
|---|---|---|
| Mock burst (this report) | ~0.07s per test | Weekly CI / manual |
| Real-Redis peak-cap validation | Real-Oracle run under concurrent jobs | Pre-production gate (manual) |
| Soak (weekly) | 30min default / 120min dispatch | `test_soak_workload.py` nightly/weekly lane |

---

## Metrics

### Mock burst results (2026-06-20)

**Test runner:** `pytest tests/stress/test_wip_worker_stress.py --run-stress -v -s`
**Environment:** mes-dashboard conda env, Python 3.11.14, no Redis, no Oracle (all mocked)

| metric | value |
|---|---|
| N (burst size) | 20 |
| peak_concurrent (recording CM) | 20 |
| enters | 20 |
| exits | 20 |
| slot leak | 0 |
| elapsed | 0.07s |
| errors | 0 |

**Mixed-fault test (17 success / 4 injected fault — indices 0, 5, 10, 15):**

| metric | value |
|---|---|
| N (burst size) | 20 |
| completed | 16 |
| faulted | 4 |
| enters | 20 |
| exits | 20 |
| slot leak after fault | 0 |

**Both tests: PASSED.**

---

## Thresholds

| threshold | mock-run status | real-Redis gate status |
|---|---|---|
| All N=20 jobs complete | PASS | pending (pre-production) |
| enters == exits (no slot leak) | PASS | pending |
| Mixed-fault: 4 faults, 16 success, enters==exits | PASS | pending |
| peak ≤ HEAVY_QUERY_MAX_CONCURRENT (3) | NOT ASSERTED — recording CM has no cap | **required before activation** |
| No deadlock (all threads join within 60s) | PASS | pending |
| Oracle session headroom: 1 conn/slot | N/A (mock Oracle) | **required before activation** |

### Why peak == N in mock mode

The recording contextmanager (`_recording_cm_factory`) simulates Oracle I/O with `time.sleep(0.02)` but does NOT enforce the Redis-backed concurrency cap (`HEAVY_QUERY_MAX_CONCURRENT=3`). All 20 threads enter the CM simultaneously before any exits, so `peak_concurrent = 20`. This is structurally correct: the test proves **wiring completeness** (every job enters and exits the slot CM exactly once), not **cap enforcement** (which requires a real Redis run and is a pre-production gate).

---

## Mock Wiring Evidence

### What the N=20 mock burst proves

1. **Slot wiring completeness:** Every call to `execute_wip_detail_job` enters `heavy_query_slot` exactly once (`enters == N`) and exits it exactly once (`exits == N`) — including when the Oracle phase raises a `RuntimeError`. This is the AC-8 wiring guarantee: no double-acquire, no leak, no bypass.

2. **Exception safety:** The `with heavy_query_slot(...)` contextmanager's `finally` branch releases the slot on `RuntimeError` from `execute_wip_detail_oracle_query`. The mixed-fault test confirms `enters == exits == 20` with 4 injected faults — zero slot leak.

3. **No deadlock:** All 20 threads complete within the 60s join timeout.

4. **Progress milestone wiring:** `update_job_progress` is called at milestones 5, 15, 90, 100 (mocked at test level; verifiable by unit test in `test_wip_worker_semaphore.py`).

### What mock tests do NOT prove

- That `HEAVY_QUERY_MAX_CONCURRENT = 3` is respected under concurrent real jobs (no Redis in CI).
- That Oracle connection pool headroom is sufficient for N concurrent WIP detail workers.
- That spool writes (`wip_dataset` namespace) complete without file-system or parquet engine errors under load.

These are pre-production gates, not pre-merge gates. The worker ships inert (no `app.py` import) until these gates are satisfied.

### Test run command

```
conda run -n mes-dashboard pytest tests/stress/test_wip_worker_stress.py --run-stress -v -s -m stress
```

Output excerpt:
```
[wip-stress] N=20 peak_concurrent=20 HEAVY_QUERY_MAX_CONCURRENT=3 elapsed=0.07s enters=20 exits=20
PASSED
[wip-stress-mixed] N=20 completed=16 faulted=4 enters=20 exits=20
PASSED
```

---

## Pre-Production Gates (required before worker activation)

The worker activation sequence per `ci-gates.md §Promotion Policy` requires the following gates to be satisfied before adding the `app.py` import line and deploying `mes-dashboard-wip-worker.service`.

### Gate 1: Real-Redis peak-cap validation

Under concurrent `"wip-detail"` RQ jobs with real Redis:

- Peak simultaneous Oracle-phase executions must be ≤ `HEAVY_QUERY_MAX_CONCURRENT` (3).
- Sample `get_active_slot_count()` during burst to confirm the Redis sorted-set cap is enforced.
- Run against a staging environment with Redis and Oracle available.
- Confirm zero slot leak after all jobs reach terminal state.

**WIP detail connection model (D2):** WIP detail is a single primary query — ONE Oracle connection per slot. This differs from the resource worker (which uses 2 connections per slot for base+OEE fan-out). The Oracle session budget in ADR 0011 must be confirmed to accommodate the new WIP worker quota: if `HEAVY_QUERY_MAX_CONCURRENT = 3` and all other domains also hold 3 slots simultaneously, the total Oracle session demand increases by 3 (not 6 as it would for resource).

### Gate 2: AC-7 resolution (camelCase assembly layer)

Before activation, the camelCase assembly layer must be implemented and the `xfail(strict=True)` marker removed from the schema-parity test in `tests/integration/test_wip_worker_integration.py`. The spool carries raw lot-row parquet; the async-result assembly endpoint must recompute summary fields (totalLots, etc.) from parquet rows — this is the open AC-7 risk documented in design.md.

### Gate 3: Activation sequence per ci-gates.md

1. Obtain sign-off on this `stress-soak-report.md` (Pre-Production Gate 5 evidence, real-Redis run results appended here).
2. Add `import src.mes_dashboard.services.wip_query_job_service  # noqa: F401` to `app.py` alongside sibling workers.
3. Deploy `deploy/mes-dashboard-wip-worker.service`; verify `wip-query` queue appears in Admin Dashboard worker status.
4. Verify `rq_monitor_service._QUEUE_NAMES` includes `os.getenv("WIP_WORKER_QUEUE", "wip-detail-query")`.
5. Confirm `wip_dataset` in `spool_routes._ALLOWED_NAMESPACES` is live.

---

## Soak Test (weekly gate)

**Existing soak suite:** `tests/integration/test_soak_workload.py`

The soak suite is a **weekly-lane** item, not a pre-merge gate (per test-layer governance and `ci-gates.md §Tier 4`). It runs for 30min default (1800s) or up to 120min on `workflow_dispatch`.

**WIP domain parametrization:** The current soak suite uses a fixed endpoint rotation (`_TRAFFIC_ENDPOINTS`) covering 6 endpoints — none of which are WIP detail async paths. WIP worker soak coverage is therefore NOT currently parametrized in `test_soak_workload.py`.

**Required action before promotion:** After worker activation (Gate 3 above), the WIP detail async path (`POST /api/wip/detail` above-L3) should be added to `_TRAFFIC_ENDPOINTS` in `test_soak_workload.py` to detect:
- Memory/RSS growth from unreleased spool parquet files.
- Oracle connection pool drift under sustained WIP async load.
- `wip_dataset` Redis key TTL expiry without file handle leaks.

Until WIP is added to the soak endpoint rotation, the existing soak test provides coverage for the gunicorn worker metrics and RQ infra health but does not exercise the WIP-specific async path.

---

## Commands / Workflows

### Tier-4 weekly mock burst (CI)
```bash
pytest tests/stress/test_wip_worker_stress.py -m stress --run-stress -v
```

### Pre-production real-Redis burst (manual, staging only)
```bash
# Requires: Redis up, Oracle up, wip_query_job_service imported in app.py (inert-off branch)
# 1. Start gunicorn + wip worker
# 2. Enqueue N concurrent wip-detail jobs via API
# 3. Poll get_active_slot_count() via /internal/metrics or admin endpoint
# 4. Confirm peak ≤ HEAVY_QUERY_MAX_CONCURRENT=3
# 5. Confirm zero active slots after all jobs complete
# 6. Record Oracle session high-water mark from DBA
```

### Soak (weekly CI)
```bash
SOAK_DURATION_SECONDS=1800 SOAK_INTERVAL_SECONDS=30 \
  pytest tests/integration/test_soak_workload.py --run-integration-real -m soak
```

---

## Results

| test | status | date |
|---|---|---|
| `test_burst_peak_bounded_no_leak` (mock, N=20) | PASSED | 2026-06-20 |
| `test_burst_no_deadlock_with_mixed_success_failure` (mock, N=20, 4 faults) | PASSED | 2026-06-20 |
| real-Redis peak-cap validation | PENDING — pre-production gate | — |
| DBA Oracle session headroom (1 conn/slot) | PENDING — pre-production gate | — |
| Soak (WIP domain added to rotation) | PENDING — post-activation | — |

---

## Failure Triage

### Stub failure: `oracledb.exceptions.NotSupportedError DPY-3001` (resolved)

**Root cause:** The original backend-engineer stub applied `patch.object(svc, ...)` and `patch("...")` context managers inside thread functions. `unittest.mock.patch` is not thread-safe when N=20 threads concurrently enter/exit the same `patch` context manager targeting the same module attribute. Some threads observed the un-patched (real) `execute_wip_detail_oracle_query`, which attempted a bequeath Oracle connection (thin-mode env) and raised `DPY-3001`.

**Fix:** All patches moved to test-method level via `monkeypatch.setattr`. A single globally-visible attribute replacement is thread-safe because it is a simple Python assignment, not a context-manager enter/exit sequence. No per-thread patch context managers remain.

**Verification:** Both tests pass with the fixed wiring. `enters == exits == 20` in both success and fault scenarios.

### Expected pre-production failure pattern

If `HEAVY_QUERY_MAX_CONCURRENT` is set below the observed concurrent job count in a real-Redis run, `acquire_heavy_query_slot` will return `False` for excess jobs. The slot CM yields `False` (fail-open) and the Oracle query proceeds — this is intentional per ADR 0011 (fail-open design). DBA headroom confirmation is still required to validate the absolute session count does not exceed the Oracle server limit.
