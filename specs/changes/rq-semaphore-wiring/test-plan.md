---
change-id: rq-semaphore-wiring
schema-version: 0.1.0
last-changed: 2026-06-20
risk: high
tier: 1
---

# Test Plan: rq-semaphore-wiring

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 (peak ≤ MAX_CONCURRENT under N=8) | integration | `tests/integration/test_rq_semaphore_wiring.py::TestConcurrencyCap::test_peak_oracle_concurrent_bounded` | 1 |
| AC-2 (all N complete, no deadlock) | integration | `tests/integration/test_rq_semaphore_wiring.py::TestConcurrencyCap::test_all_jobs_complete_no_deadlock` | 1 |
| AC-3 (zero slot leak post-run) | integration | `tests/integration/test_rq_semaphore_wiring.py::TestConcurrencyCap::test_semaphore_fully_released_after_run` | 1 |
| AC-4 (exception releases slot) | unit | `tests/test_rq_semaphore_wiring.py::TestHeavyQuerySlotCM::test_slot_released_on_oracle_exception` | 1 |
| AC-4 (next job acquires after exception) | unit | `tests/test_rq_semaphore_wiring.py::TestHeavyQuerySlotCM::test_next_job_acquires_after_exception` | 1 |
| AC-5 (flag-off: query-tool no slot acquire) | unit | `tests/test_rq_semaphore_wiring.py::TestFlagOffParity::test_query_tool_flag_off_no_slot_acquire` | 1 |
| AC-5 (flag-off: hold no slot acquire) | unit | `tests/test_rq_semaphore_wiring.py::TestFlagOffParity::test_hold_flag_off_no_slot_acquire` | 1 |
| AC-5 (flag-off: resource no slot acquire) | unit | `tests/test_rq_semaphore_wiring.py::TestFlagOffParity::test_resource_flag_off_no_slot_acquire` | 1 |
| AC-6 (query-tool: exactly-once, Oracle-phase only) | unit | `tests/test_rq_semaphore_wiring.py::TestPerWorkerWiring::test_query_tool_slot_acquired_once` | 1 |
| AC-6 (hold: exactly-once, Oracle-phase only) | unit | `tests/test_rq_semaphore_wiring.py::TestPerWorkerWiring::test_hold_slot_acquired_once` | 1 |
| AC-6 (resource: exactly-once, Oracle-phase only) | unit | `tests/test_rq_semaphore_wiring.py::TestPerWorkerWiring::test_resource_slot_acquired_once` | 1 |
| AC-6 (reject: no job-level acquire — AST proof) | unit | `tests/test_rq_semaphore_wiring.py::TestRejectWorkerAbsence::test_reject_job_has_no_job_level_acquire` | 1 |
| AC-6 (CM helper: yields bool; guards release on fail-open) | unit | `tests/test_global_concurrency.py::TestHeavyQuerySlotCM` (extend existing file) | 1 |
| AC-7 (no new env var) | contract | `tests/test_env_contract.py` (extend existing, assert key count unchanged) | 1 |
| AC-1..AC-3 (burst N=20, no leak) | stress | `tests/stress/test_rq_semaphore_stress.py::TestSemaphoreStress::test_burst_peak_bounded_no_leak` | 4 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 1 | Per-worker wiring assertions; CM helper; reject AST absence; exception release; flag-off parity |
| integration | 1 | N=8 concurrent mock workers with peak-sampling via patched CM; no deadlock; zero leak |
| contract | 1 | Env-contract read-only assertion — no new key introduced (extend `tests/test_env_contract.py`) |
| stress | 4 | N=20 burst; real-time `get_active_slot_count()` sampling; weekly gate (`@pytest.mark.stress`) |

## Test Update Contract

| existing test | action | reason |
|---|---|---|
| `tests/test_global_concurrency.py` | extend (add `TestHeavyQuerySlotCM` class) | New `heavy_query_slot()` CM helper added to `global_concurrency.py` |

## Stop Rules

- Do not run broad pytest before targeted and changed-area phases pass.
- Do not investigate more than the first failure per phase.
- Do not classify any failure as known, pre-existing, waived, or allowed.
- If full suite fails, record the first failure and block the gate.

## Out of Scope

- E2E / browser tests — no UI surface changes.
- `heavy_query_telemetry.py` counters — D5 explicitly defers acquire-latency metrics to a follow-up.
- `reject_query_job_service.py` wiring (job-level) — reject is already wired at cache layer; only AST absence verified.
- `ensure_canonical_spool` Oracle-phase bracketing — explicitly deferred per design D3.
- DBA headroom validation for resource 2-connection fan-out — operational confirmation, not a test item.

## Notes

- Extend `tests/test_global_concurrency.py` with `TestHeavyQuerySlotCM`; do not duplicate existing `TestAcquireHeavyQuerySlot` cases.
- AC-6 reject absence: use `ast.parse()` + walk `ast.Call` per test-discipline.md; assert `acquire_heavy_query_slot` absent at job level in `execute_reject_query_job`.
- Integration peak-sampling: patch `heavy_query_slot` CM to record entry/exit timestamps; compute max overlap; assert ≤ `HEAVY_QUERY_MAX_CONCURRENT` (3).
- Flag-off unit tests: use `monkeypatch.setattr` on module-level flag constant (frozen at import), not `os.environ`.
- Stress test carries `@pytest.mark.stress`; excluded from Tier-1 pre-merge gate.
