# Spec: Multi-Worker Concurrency Test Coverage

## Purpose

Define requirements for an integration test suite that exercises real RQ worker subprocesses against a shared Redis instance, verifying correctness of concurrent job execution, deduplication, distributed locking, result integrity, and queue fairness.

---

## Requirements

### Requirement: Multi-worker concurrency tests SHALL exist as integration suite
The repository SHALL contain `tests/integration/test_multi_worker_concurrency.py` that exercises real RQ worker subprocesses against a shared Redis instance, marked with `@pytest.mark.multi_worker` so it can be filtered independently.

#### Scenario: Marker filter selects multi-worker tests
- **WHEN** `pytest -m multi_worker` runs
- **THEN** only multi-worker concurrency tests SHALL execute

#### Scenario: Tests skip gracefully when Redis is unavailable
- **WHEN** the test fixture cannot reach Redis
- **THEN** tests SHALL `pytest.skip` with a clear message rather than fail

---

### Requirement: A reusable multi-worker harness SHALL manage worker subprocess lifecycle
`tests/integration/_multi_worker_harness.py` SHALL provide a fixture or context manager that (a) spawns N RQ worker subprocesses against an isolated Redis db, (b) provides a Redis-based barrier for deterministic synchronisation, (c) collects worker stdout/stderr, (d) terminates and cleans up reliably.

#### Scenario: Harness spawns and terminates workers cleanly
- **WHEN** a test enters the harness fixture with `worker_count=3`
- **THEN** 3 RQ worker subprocesses SHALL be started and become ready (verified by ping or pub/sub readiness signal)
- **WHEN** the test ends (pass or fail)
- **THEN** all worker subprocesses SHALL be terminated within 5 seconds (`SIGTERM` then `SIGKILL` fallback)

#### Scenario: Harness isolates Redis state
- **WHEN** the harness fixture starts
- **THEN** the test SHALL connect to a Redis db reserved for testing (e.g. db 15)
- **THEN** the harness SHALL `FLUSHDB` before and after each test

#### Scenario: Harness exposes a deterministic barrier
- **WHEN** N workers concurrently invoke `barrier.wait("phase_1", n=N)`
- **THEN** all N invocations SHALL return only after every worker has reached the barrier
- **THEN** no `time.sleep` SHALL be required for the test to pass deterministically

---

### Requirement: Tests SHALL verify job idempotence after worker crash
A test SHALL submit a job whose function records its own execution side-effect to Redis, force-kill the worker holding it mid-execution, and verify the job is re-picked by another worker without producing duplicate side-effects.

#### Scenario: Job rerun after SIGKILL produces no duplicate side-effect
- **WHEN** worker A acquires job J and is killed with SIGKILL before completing
- **AND** worker B subsequently picks up J
- **THEN** the side-effect list (RPUSH count) for J SHALL contain exactly one terminal "completed" record after both workers finish
- **THEN** no orphan in-progress markers for J SHALL remain in Redis after the test

---

### Requirement: Tests SHALL verify export deduplication under concurrent submission
A test SHALL submit two export jobs with identical fingerprints to two different workers simultaneously and verify only one execution occurs while the other reads the cached result.

#### Scenario: Concurrent export with identical fingerprint executes once
- **WHEN** worker A and worker B simultaneously receive export requests with identical fingerprint F
- **AND** both reach the deduplication check inside a barrier-synchronised window
- **THEN** the underlying export-producing function SHALL be invoked exactly once (verified via side-effect counter)
- **THEN** both workers SHALL return a result referring to the same artifact

---

### Requirement: Tests SHALL verify stale lock recovery after holder crash
A test SHALL acquire a distributed lock on worker A, crash worker A, and verify that subsequent contenders cannot acquire the lock before its TTL expires AND can acquire it after expiry.

#### Scenario: Lock not claimable before TTL expiry
- **WHEN** worker A holds lock L with TTL T and is killed
- **AND** worker B attempts to acquire L within T/2 of the kill time
- **THEN** worker B's acquire attempt SHALL fail (or block) until at least T elapses

#### Scenario: Lock claimable after TTL expiry
- **WHEN** worker A holds lock L with TTL T and is killed
- **AND** worker B attempts to acquire L after T + small grace period
- **THEN** worker B SHALL successfully acquire L

---

### Requirement: Tests SHALL verify result write/read race safety
A test SHALL have worker A write a result while worker B reads concurrently, repeated across many barrier-synchronised rounds, and verify worker B never observes a partially-written value.

#### Scenario: Reader observes complete value during concurrent write
- **WHEN** worker A is writing result R for key K
- **AND** worker B reads K within the same barrier window
- **THEN** every read SHALL return either the previous complete value or the new complete value
- **THEN** no read SHALL return a partially-serialised, truncated, or otherwise structurally invalid value across at least 100 barrier-synchronised rounds

---

### Requirement: Tests SHALL verify queue fairness with no permanent starvation
A test SHALL submit M jobs (M >> N) to a single queue with N workers and verify every worker processes at least one job within the test window.

#### Scenario: All workers receive at least one job under load
- **WHEN** 30 trivial jobs are enqueued to one queue with 3 workers active
- **THEN** every worker SHALL process at least one job before the queue is drained
- **THEN** no worker SHALL remain idle while jobs are still queued

---

### Requirement: Tests SHALL surface worker subprocess output on failure
When a test assertion fails or a worker crashes unexpectedly, the captured stdout/stderr from each worker subprocess SHALL be printed in the test report to aid debugging.

#### Scenario: Worker logs printed on assertion failure
- **WHEN** a multi-worker test fails any assertion
- **THEN** the test report SHALL include a section per worker showing the captured stdout and stderr (or a clear "no output" marker)
