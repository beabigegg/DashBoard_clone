## 1. Pre-flight Investigation

- [x] 1.1 Identify production lock TTL values (search `lock` / `setnx` / `acquire` in `src/mes_dashboard/`) and document expected upper-bound for tests
- [x] 1.2 Identify export deduplication entry point and fingerprint computation function
- [x] 1.3 Confirm CI runner can spawn subprocesses and reach Redis (single Redis db 15 reserved for tests)

## 2. Test Harness Infrastructure

- [x] 2.1 Create `tests/integration/_multi_worker_harness.py` with `MultiWorkerHarness` class managing worker subprocess lifecycle
- [x] 2.2 Implement `WorkerBarrier` (Redis INCR + BLPOP based deterministic synchronisation primitive)
- [x] 2.3 Implement worker stdout/stderr capture; expose `harness.worker_logs` for assertion / debug
- [x] 2.4 Add `pytest_runtest_makereport` hook (or per-test fixture) that prints worker logs on failure
- [x] 2.5 Implement clean teardown: SIGTERM → wait 5s → SIGKILL fallback; FLUSHDB before & after each test
- [x] 2.6 Register `multi_worker` marker in `pytest.ini`

## 3. Mock Job Functions for Side-effect Observation

- [x] 3.1 Create `tests/integration/_multi_worker_jobs.py` with mock job functions that RPUSH execution records (PID, timestamp, job_id, side-effect counter) to Redis
- [x] 3.2 Add helper `read_side_effects(redis, job_id) -> list[dict]` to load and parse records for assertions
- [x] 3.3 Document side-effect record schema in module docstring

## 4. Concurrency Tests

- [x] 4.1 `test_job_idempotence_after_crash`: crash worker mid-execution, verify exactly one terminal side-effect after re-pickup
- [x] 4.2 `test_export_deduplication_under_concurrent_submission`: two workers, identical fingerprint, verify single execution
- [x] 4.3 `test_stale_lock_not_claimable_before_ttl`: kill lock holder, contender blocks until TTL expires
- [x] 4.4 `test_stale_lock_claimable_after_ttl`: contender succeeds after TTL + grace
- [x] 4.5 `test_result_write_read_race_safety`: 100 rounds of concurrent write/read, no partial reads
- [x] 4.6 `test_queue_fairness_no_starvation`: 30 jobs / 3 workers, every worker processes ≥ 1

## 5. Stability & Local Verification

- [x] 5.1 Run `pytest -m multi_worker -v` locally 10 times; record any flake; fix root cause (no `time.sleep` workarounds)
- [x] 5.2 Run with `--lf` after a deliberate forced failure to verify worker logs surface correctly
- [x] 5.3 Verify cleanup: after test run, no leftover worker processes (`ps aux | grep "rq worker"`) and Redis db 15 is empty

## 6. CI Integration

- [x] 6.1 Add CI step `pytest -m multi_worker` as a separate job (allows independent retry / longer timeout)
- [x] 6.2 Configure CI step to capture and upload worker log artifacts on failure
- [x] 6.3 Set CI timeout for this step to 5 minutes (well above expected 60-120s)

## 7. Documentation & Follow-ups

- [x] 7.1 Update `CLAUDE.md` "Project Commands" section with `pytest -m multi_worker` entry
- [x] 7.2 Add `tests/integration/README.md` (or section in existing README) explaining harness usage and how to add a new multi-worker test
- [x] 7.3 If any concurrency test surfaces a real production bug, open a follow-up issue (do NOT fix in this change); document the link in `proposal.md` "Impact" section
- [x] 7.4 Run `openspec validate add-rq-multi-worker-concurrency --strict` and address any issues
