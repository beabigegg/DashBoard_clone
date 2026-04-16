## Context

The project already has three test tiers: pytest unit tests (~155), node:test/vitest frontend tests (~33), and `tests/e2e/` in-process Flask test client E2E (~27). `qa-coverage-hardening` extended all three. The remaining gaps require a **fourth tier**: tests that boot real subprocesses against real infrastructure. Specifically:

- `tests/test_distributed_lock.py` is already marked `@pytest.mark.integration` and uses real Redis, but its concurrency model is `threading.Thread` — same process, shared GIL, shared memory. Real bugs around fork-based gunicorn workers (separate file descriptor tables, separate Python process state, separate Oracle connection pools) cannot surface here.
- `tests/test_cross_worker_result_sharing.py` uses fakeredis + threads, so it tests the *invariant* (atomic rename, metadata-after-write) but cannot test the *infrastructure* (real shared volume, real OS scheduler).
- `frontend/tests/playwright/` exists with three specs (`hold-overview`, `query-tool`, `reject-history`) running against a local server on port 8080. None of them test the unload/abandon path.

The infrastructure cost of a real-environment test tier is real — boot time, port management, cleanup robustness — but for the four scenarios this change covers, mocks have already proven inadequate.

## Goals / Non-Goals

**Goals:**
- Add the **four** highest-value real-environment tests: tab-close abandon, multi-process spool round-trip + lock cross-process exclusion, Redis chaos for fail-mode behaviour, shared-volume detection.
- Establish a reusable conftest fixture set (`gunicorn_workers`, `local_redis`, `temp_spool_dir`) so future real-environment tests are cheap to add.
- Gate the new tier behind a CLI flag (`--run-integration-real`) so it does not slow pre-merge CI.
- Make the shared-volume mismatch detectable at app startup, not just in tests.

**Non-Goals:**
- Replacing or removing existing thread-based tests. They are fast and useful for the invariants they cover.
- Building a containerised test harness (Docker Compose, testcontainers). The fixtures use plain subprocess; container support can come later.
- Migrating to a real database (Oracle) for these tests. Oracle tests are out of scope; the multi-worker test uses a no-op Oracle stub via dependency injection.
- Adding alerting/dashboards on the new metrics (`mes.spool.shared_volume_mismatch`). Wiring is left to ops.
- Writing five tests when four cover the gaps. The user explicitly listed real Playwright unload + real multi-process + real Redis chaos + shared volume as the high-value items.

## Decisions

### 1. Subprocess-based, not container-based

**Decision**: Use `subprocess.Popen` for both gunicorn workers and the temp Redis instance. No Docker Compose, no testcontainers.

**Alternatives considered:**
- *testcontainers-python*: pulls Docker images, slow first run, requires Docker daemon — adds CI complexity for the four-test scope we care about.
- *Docker Compose orchestration*: same problem, plus it makes the tests harder to run locally for a developer who just wants to debug one.
- *Pytest-xdist worker isolation*: gives us multi-process Python but not multi-process gunicorn; doesn't exercise the real WSGI worker model.

The subprocess approach is portable (works on any machine with `redis-server` and `gunicorn` already installed, both of which are project dependencies), debuggable (you can `subprocess.Popen(..., stdout=sys.stderr)` and watch logs live), and cheap (no image pull, no daemon).

### 2. Tests live under `tests/integration/`

**Decision**: New test directory `tests/integration/` with its own `conftest.py`. Tests are gated by both a marker (`@pytest.mark.integration_real`) AND a CLI flag (`--run-integration-real`). Skipped unconditionally otherwise.

**Rationale**: Marker alone is not enough — we want CI runners that don't pass the flag to skip the tier even if they collect the marker. CLI flag alone hides the marker from `pytest --markers`. Both together is the project pattern (see `--run-integration` and `--run-e2e`).

### 3. Playwright test asserts via API poll, not via internal helper

**Decision**: After `page.close()`, the test polls `GET /api/job/<id>?prefix=<p>` until `status="abandoned"` or 5-second timeout. No new "test-only" backdoor endpoint.

**Alternatives considered:**
- *Reading Redis directly from the test process*: works, but couples the test to Redis internals and bypasses the API contract we actually care about.
- *Adding a `/test/job-state/<id>` debug endpoint*: introduces a production attack surface for one test.

The polling approach exercises the same API the real frontend uses, so we're testing the actual user-visible contract.

### 4. Fixture: `gunicorn_workers(n_workers, spool_dir, redis_url)`

**Decision**: Yields a list of `(pid, port)` tuples after `/health` returns 200 on each. Tears down with SIGTERM, waits 5s, escalates to SIGKILL. Logs go to `tmp_path/gunicorn-{i}.log` for failure debugging.

**Implementation sketch:**

```python
@pytest.fixture
def gunicorn_workers(tmp_path, local_redis, temp_spool_dir):
    workers = []
    for i in range(2):
        port = _find_free_port()
        env = os.environ | {
            "GUNICORN_BIND": f"127.0.0.1:{port}",
            "GUNICORN_WORKERS": "1",
            "REDIS_URL": local_redis,
            "REDIS_CONTROL_URL": local_redis,
            "QUERY_SPOOL_DIR": str(temp_spool_dir),
        }
        log = (tmp_path / f"gunicorn-{i}.log").open("w")
        proc = subprocess.Popen(
            ["gunicorn", "-c", "gunicorn.conf.py", "src.mes_dashboard.app:app"],
            env=env, stdout=log, stderr=log,
        )
        _wait_for_health(f"http://127.0.0.1:{port}/health", timeout=15)
        workers.append((proc.pid, port))
    yield workers
    for pid, _ in workers:
        os.kill(pid, signal.SIGTERM)
    # ... reap with timeout ...
```

### 5. Fixture: `local_redis(port)`

**Decision**: Spawn `redis-server --port <p> --maxmemory 16mb --maxmemory-policy noeviction --save ""` in subprocess. Wait for `PING`. Yield the URL. Tear down with `redis-cli -p <p> SHUTDOWN NOSAVE`.

**Rationale**: Each test gets a clean Redis. The 16mb cap makes the eviction test reachable. `--save ""` prevents the temp instance from writing dump files. Two instances (cache plane + control plane) are spawned for the chaos test.

### 6. Shared volume probe

**Decision**: At `app.py` startup, write `<QUERY_SPOOL_DIR>/_shared_volume_probe.json` with `{"pid": os.getpid(), "boot_at": <ts>, "hostname": ...}`. Each gunicorn worker writes its own probe with a unique key (`probe_{pid}.json`). A background check in `spool_dir_check.py` verifies that the probe of at least one *other* gunicorn worker is visible within 30 seconds of boot — if not, log ERROR and increment `mes.spool.shared_volume_mismatch`.

**Limitations**: Only triggers if there are 2+ workers. Single-worker dev setups skip the check. Documented.

### 7. Conda env discipline

**Decision**: All test commands documented as `conda run -n mes-dashboard pytest ...`. Per the user's CLAUDE.md hard rules. The fixture itself does not call conda — it assumes the pytest process is already inside the env.

## Risks / Trade-offs

- **[Port conflicts]** → `_find_free_port()` uses `socket.bind(('', 0))` then closes — race window with another process. Mitigation: fixture retries up to 3 times.
- **[Slow boot]** → gunicorn cold start + worker init + `/health` poll = 5-15 seconds per test. Total tier runtime ~60-120s. Acceptable for a nightly run, too slow for pre-merge. Documented.
- **[Flaky cleanup]** → If a test crashes between Popen and teardown, gunicorn workers leak. Mitigation: register an `atexit` handler in conftest that SIGKILLs anything tagged with the test's tmp_path; CI runners are ephemeral so worst case is one stuck process per failed run.
- **[Shared cache for Playwright]** → Per project rules, DO NOT run `playwright install`. The fixture uses `PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright` which is already configured in `frontend/playwright.config.js:21`. Verified.
- **[Real Redis on CI runner]** → Requires `redis-server` binary. Already a project dependency for `test_distributed_lock.py` integration tier. Document the requirement in the README/CI docs.
- **[`integration_real` marker discoverability]** → Add it to `pytest.ini` `markers` list so `pytest --markers` shows it. Otherwise developers won't know it exists.
- **[Dependency coupling]** → This change cannot land before `fix-job-owner-auth` and `redis-lock-policy` because the assertions reference behaviour those changes introduce. The user has explicitly chosen sequential development, so the dependency is fine — this change is #4 in the order.

## Migration Plan

1. Land `fix-job-owner-auth` and `redis-lock-policy` first (per the sequenced development plan).
2. Land this change. The new tests start green (because the dependencies are satisfied).
3. Add the nightly CI job that runs `pytest tests/integration/ --run-integration-real` (out of scope for this change — left for ops).
4. Watch the first week of nightly runs for flakes; tune the `_wait_for_health` timeout if needed.
5. Promote any test from "nightly only" to "pre-merge" only after it has been green for 50+ runs.

**Rollback**: revert the PR. The new test files and fixtures go away. The `spool_dir_check` startup probe should stay even on rollback because it is a useful production safeguard, not just a test scaffold — if rolling back, leave that file in place.

## Open Questions

*(none — sequencing and scope decided up front)*
