## Why

`qa-coverage-hardening` added breadth: 25+ new pytest files, vitest migration, route contract sweep, schema guards. It deliberately stayed at the unit/in-process layer so it could land quickly. The remaining gaps are the ones that **only show up against real infrastructure**:

1. **Real browser sendBeacon on tab close** — `frontend/src/portal-shell/main.js:65-78` fires `sendBeacon` on `beforeunload` and `qa-coverage-hardening` added the abandon endpoint. But there is **no test** that actually closes a real browser tab and verifies the server received the beacon and marked the job abandoned. A unit test of the registry helper does not prove the browser fired the beacon.
2. **True multi-process gunicorn behaviour** — `tests/test_distributed_lock.py` uses `threading.Thread` (same process), and `tests/test_cross_worker_result_sharing.py` uses fakeredis + threads. Neither exercises real fork-based gunicorn workers writing to a shared spool directory and reading each other's parquet files. The bugs we worry about (file descriptor races, OS scheduler quirks, cross-worker SIGTERM) are invisible under thread-based tests.
3. **Redis chaos** — `redis_client.py` has reconnection logic that is never tested under real outage. `redis-lock-policy` adds the fail-mode contract but its unit tests use monkeypatch fault injection. We need a chaos-style integration test that actually stops/starts Redis and verifies cache plane vs control plane behave as designed.
4. **Shared volume detection** — `qa-coverage-hardening` proposal mentioned "`QUERY_SPOOL_DIR` 啟動時驗證共用 volume" but the agent investigation found no such check actually implemented. If two gunicorn workers run on machines with separate volumes (mis-deployed), spool round-trip silently breaks.

These four gaps share a property: they are expensive to test (real subprocess, real Redis lifecycle, real browser) and slow to run. They belong in an integration tier, not pre-merge unit tests. This change creates that tier and fills it with the four highest-value tests.

## What Changes

- **NEW Playwright test** `frontend/tests/playwright/job-abandon-on-unload.spec.js`: log in, start an async query whose worker entry deliberately sleeps, capture the job_id from the network tab, close the tab via `page.close()`, then poll `GET /api/job/<id>?prefix=<p>` (or read Redis directly via a helper endpoint) and assert `status="abandoned"` within 5 seconds. Uses the existing `_auth.js` helper. Reuses `~/.cache/ms-playwright`. Runs against a local dev server on port 8080.
- **NEW pytest harness** `tests/integration/test_real_multi_worker.py`: marked `@pytest.mark.integration_real` (new marker). Spawns two real gunicorn workers via `subprocess.Popen` against a temp port, points them at a temp `QUERY_SPOOL_DIR` and a real local Redis, then exercises:
  - Worker A enqueues + executes a job → spool file appears → Worker B's view endpoint reads it back and returns the same data.
  - Worker A holds a `try_acquire_lock` → Worker B's identical call returns `False` (verifies cross-process exclusion is real).
  - Kill Worker A mid-job (SIGTERM) → assert the job's TTL eventually expires the lock and Worker B can re-acquire.
- **NEW pytest harness** `tests/integration/test_redis_chaos.py`: marked `@pytest.mark.integration_real`. Uses a fixture that starts/stops a dedicated Redis instance on a non-default port. Verifies:
  - Cache plane keys survive control plane outage (and vice versa).
  - When control-plane Redis is killed mid-flight, `try_acquire_lock(..., fail_mode="closed")` returns `False` and the cache refresh skips (depends on `redis-lock-policy` being landed).
  - When control-plane Redis is killed mid-flight, `try_acquire_lock(..., fail_mode="raise")` raises `LockUnavailableError`.
  - After Redis restart, the next acquisition succeeds without restarting the gunicorn process (verifies the redis-py reconnection backoff).
  - When cache-plane Redis is filled past `maxmemory` and `allkeys-lru` triggers eviction, control-plane lock keys are NOT evicted (verifies `noeviction` policy on the control plane).
- **NEW startup check** `src/mes_dashboard/core/spool_dir_check.py`: at app startup, write a `_shared_volume_probe.txt` containing the current PID into `QUERY_SPOOL_DIR`. If multiple gunicorn workers or RQ workers see different probes (or none), log an ERROR and emit a `mes.spool.shared_volume_mismatch` metric. The check itself runs in `app.py` startup; the cross-worker assertion runs as part of `test_real_multi_worker.py`.
- **NEW pytest marker** `integration_real` registered in `pytest.ini` / `conftest.py`. Gated behind a `--run-integration-real` CLI flag. Skipped by default. CI pipeline has a separate "nightly" job that runs it.
- **NEW conftest fixtures** `tests/integration/conftest.py`:
  - `gunicorn_workers(n_workers, spool_dir, redis_url)` — spawns N gunicorn processes via subprocess, waits for `/health` to return 200, yields a list of `(pid, port)` tuples. Tears down with SIGTERM + reap.
  - `local_redis(port)` — spawns a `redis-server` subprocess with a temp config file, waits for `PING` to succeed, yields the URL. Tears down with SHUTDOWN NOSAVE.
  - `temp_spool_dir()` — `tmp_path` wrapper that sets `QUERY_SPOOL_DIR` env var.
- **NEW CI job** documented (not implemented in this change — left for ops to add): nightly run of `pytest tests/integration/ --run-integration-real`. Failure pages on-call.

## Capabilities

### New Capabilities
- `real-environment-integration-tests`: subprocess-based test tier exercising real gunicorn workers, real Redis, real browser via Playwright, and real shared-volume checks. Defines the `integration_real` marker, the conftest fixtures, and the four canonical tests.

### Modified Capabilities
*(none directly — depends on `fix-job-owner-auth` and `redis-lock-policy` for the assertions to make sense)*

## Impact

- **Affected code**:
  - `src/mes_dashboard/core/spool_dir_check.py` (new)
  - `src/mes_dashboard/app.py` (call the startup check)
  - `tests/integration/__init__.py`, `tests/integration/conftest.py` (new)
  - `tests/integration/test_real_multi_worker.py` (new)
  - `tests/integration/test_redis_chaos.py` (new)
  - `frontend/tests/playwright/job-abandon-on-unload.spec.js` (new)
  - `pytest.ini` or `conftest.py` (new marker registration + flag)
- **Test infrastructure dependencies**:
  - Local `redis-server` binary on the test machine (already required for the existing `test_distributed_lock.py` integration tests).
  - `~/.cache/ms-playwright` shared cache (already in place per project rules — DO NOT run `playwright install`).
  - Free TCP ports for the temp gunicorn + temp Redis instances (use `socket.bind(('', 0))` to discover).
- **Dependencies on other changes**:
  - **Hard dependency on `fix-job-owner-auth`**: the Playwright test asserts that the abandoned job is associated with the same browser session, so `get_owner_token` must exist server-side.
  - **Hard dependency on `redis-lock-policy`**: the chaos test asserts on `fail_mode="closed"` and `fail_mode="raise"` semantics.
  - **Soft dependency on `query-tool-error-contract`**: only needed because `redis-lock-policy` depends on it (`LockUnavailableError` is a `MesServiceError` subclass).
- **Run cost**: the four tests collectively take ~60-120 seconds (Playwright cold start + gunicorn boot + Redis lifecycle). Too slow for pre-merge; appropriate for nightly.
- **Conda env**: tests run via `conda run -n mes-dashboard pytest tests/integration/ --run-integration-real`. Documented in tasks.
