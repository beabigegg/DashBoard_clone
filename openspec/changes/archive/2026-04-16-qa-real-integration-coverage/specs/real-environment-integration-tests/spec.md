## ADDED Requirements

### Requirement: Project SHALL provide a real-environment integration test tier
The project SHALL provide a fourth test tier under `tests/integration/` that exercises real subprocesses (gunicorn workers, Redis, browsers) instead of mocks or in-process clients. This tier SHALL be gated by both a pytest marker `integration_real` and a CLI flag `--run-integration-real`. Tests in this tier SHALL be skipped by default on developer machines and pre-merge CI; they SHALL run in a separate nightly CI job.

#### Scenario: Skipped by default
- **WHEN** `pytest tests/` is invoked without `--run-integration-real`
- **THEN** all tests under `tests/integration/` SHALL be skipped
- **THEN** the test session SHALL succeed even if the integration tier would have failed

#### Scenario: Opt-in execution
- **WHEN** `pytest tests/integration/ --run-integration-real` is invoked
- **THEN** the integration tests SHALL be collected and executed
- **THEN** the runner SHALL fail the session if any integration test fails

#### Scenario: Marker is registered
- **WHEN** `pytest --markers` is invoked
- **THEN** `integration_real` SHALL appear in the listed markers with a description

### Requirement: Real browser SHALL signal job abandonment on tab close
A Playwright test SHALL log into the dashboard, start an async query, close the browser tab, and verify that the server marks the job as abandoned within 5 seconds.

#### Scenario: Tab close triggers server-side abandon
- **WHEN** a Playwright session starts a long-running async job and then calls `page.close()`
- **THEN** the test SHALL poll `GET /api/job/<job_id>?prefix=<p>` until the response shows `status="abandoned"` or 5 seconds elapse
- **THEN** the assertion SHALL pass when the abandoned status is observed within the deadline

#### Scenario: Same browser session can abandon
- **WHEN** the test reuses the same Playwright context cookie for both the enqueue and the poll
- **THEN** the server SHALL accept the abandonment because the session token matches `meta["owner"]` (per the `fix-job-owner-auth` requirement)

### Requirement: Real multi-worker gunicorn SHALL share spool and respect cross-process locks
An integration test SHALL spawn at least two real gunicorn worker processes against a shared `QUERY_SPOOL_DIR` and a shared control-plane Redis. The test SHALL verify cross-worker spool round-trip and cross-process lock exclusion.

#### Scenario: Cross-worker spool round-trip
- **WHEN** Worker A enqueues and executes a query that writes a parquet spool file
- **THEN** Worker B's view endpoint SHALL be able to read the same spool file via `query_id`
- **THEN** the data returned by Worker B SHALL match what Worker A wrote

#### Scenario: Cross-process lock exclusion
- **WHEN** Worker A holds `try_acquire_lock("test-lock", fail_mode="closed")`
- **THEN** Worker B's identical call SHALL return `False`
- **THEN** the assertion SHALL distinguish "real cross-process exclusion" from "thread-level exclusion"

#### Scenario: Lock TTL expiry after worker crash
- **WHEN** Worker A holds a lock and is killed via SIGKILL
- **THEN** after the lock TTL expires, Worker B SHALL be able to re-acquire the same lock

### Requirement: Redis chaos test SHALL verify fail-mode and reconnect behaviour
An integration test SHALL spawn dedicated cache-plane and control-plane Redis instances, induce outages mid-flight, and verify the documented fail-mode behaviour and reconnect semantics.

#### Scenario: Control-plane outage triggers fail_mode=closed skip
- **WHEN** the control-plane Redis is killed mid-flight and a cache-refresh caller invokes `try_acquire_lock("...", fail_mode="closed")`
- **THEN** the call SHALL return `False`
- **THEN** the cache refresh SHALL skip without invoking Oracle
- **THEN** the `mes.lock.fail_mode_triggered` counter SHALL increment

#### Scenario: Control-plane outage triggers fail_mode=raise propagation
- **WHEN** the control-plane Redis is killed mid-flight and a daemon caller invokes `try_acquire_lock("...", fail_mode="raise")`
- **THEN** the call SHALL raise `LockUnavailableError`
- **THEN** the test SHALL assert the exception is caught by the daemon's expected handler

#### Scenario: Reconnect after outage
- **WHEN** the control-plane Redis is killed and then restarted
- **THEN** the next `try_acquire_lock` call SHALL succeed without restarting any gunicorn process
- **THEN** the test SHALL prove redis-py's reconnect backoff works against the real client

#### Scenario: Cache-plane eviction does not affect control-plane
- **WHEN** the cache-plane Redis is filled past `maxmemory` with `allkeys-lru` policy
- **THEN** lock keys on the control-plane Redis SHALL remain present
- **THEN** the test SHALL prove the `noeviction` policy on the control plane is honoured

### Requirement: App startup SHALL detect shared-volume mismatch
The application startup SHALL write a per-PID probe file into `QUERY_SPOOL_DIR` and run a background check that observes the probes written by other workers. If a multi-worker deployment cannot see other workers' probes within 30 seconds, the application SHALL log an ERROR and emit a `mes.spool.shared_volume_mismatch` metric.

#### Scenario: Shared volume present
- **WHEN** two gunicorn workers boot against the same physical `QUERY_SPOOL_DIR`
- **THEN** within 30 seconds each worker SHALL observe the other's probe file
- **THEN** no `mes.spool.shared_volume_mismatch` metric SHALL be emitted

#### Scenario: Volume mismatch
- **WHEN** two gunicorn workers boot against different physical paths that both resolve to `QUERY_SPOOL_DIR`
- **THEN** within 30 seconds neither worker SHALL observe the other's probe file
- **THEN** each worker SHALL log an ERROR-level message identifying the mismatch
- **THEN** the `mes.spool.shared_volume_mismatch` metric SHALL be incremented

#### Scenario: Single-worker dev mode skips check
- **WHEN** the application is started with a single gunicorn worker (e.g., local dev)
- **THEN** the probe file SHALL still be written
- **THEN** no mismatch error SHALL be logged because there are no peers to compare against

### Requirement: Conftest SHALL provide reusable real-environment fixtures
`tests/integration/conftest.py` SHALL provide three fixtures usable by any test in the tier: `gunicorn_workers`, `local_redis`, and `temp_spool_dir`. Each fixture SHALL handle setup, health-check waiting, and cleanup.

#### Scenario: gunicorn_workers fixture
- **WHEN** a test requests the `gunicorn_workers` fixture with `n_workers=2`
- **THEN** the fixture SHALL start two gunicorn processes via `subprocess.Popen` against a temp port and a temp spool dir
- **THEN** the fixture SHALL block until each worker's `/health` endpoint returns 200
- **THEN** the fixture SHALL yield a list of `(pid, port)` tuples
- **THEN** on teardown the fixture SHALL SIGTERM each worker, wait up to 5 seconds, and SIGKILL any that did not exit

#### Scenario: local_redis fixture
- **WHEN** a test requests the `local_redis` fixture
- **THEN** the fixture SHALL spawn a `redis-server` subprocess on a free port with `--save ""` and a 16mb maxmemory cap
- **THEN** the fixture SHALL block until `PING` returns `PONG`
- **THEN** the fixture SHALL yield the redis URL string
- **THEN** on teardown the fixture SHALL issue `SHUTDOWN NOSAVE`

#### Scenario: temp_spool_dir fixture
- **WHEN** a test requests the `temp_spool_dir` fixture
- **THEN** the fixture SHALL create a temp directory and set `QUERY_SPOOL_DIR` env var to its path
- **THEN** on teardown the env var SHALL be restored and the directory SHALL be removed
