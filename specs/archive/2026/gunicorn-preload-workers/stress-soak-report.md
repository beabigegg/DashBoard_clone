# Stress / Soak Report — gunicorn-preload-workers

## Status

**Planned — not yet executed.** This report documents the soak test plan and the conditions under which production clearance is granted. Actual soak execution occurs on the CI weekly schedule after merge.

## Soak Test Coverage

### Tier 4 — Restart-Loop Soak (tests/integration/test_soak_workload.py)

Test: `test_preload_workers_restart_loop_no_connection_leak`
- Executes 5 gunicorn graceful-reload cycles
- Asserts per-cycle: Oracle connection pool is fresh (no inherited FDs), no ORA errors logged, thread count stable
- Marker: `@pytest.mark.soak` — covered by weekly `soak-tests.yml` gate

### Tier 3 — Multi-Worker Fork-Safety (tests/integration/test_preload_fork_safety.py)

14 tests with `integration_real` + `multi_worker` markers covering AC-1 through AC-9. Currently implemented as `pytest.skip` stubs pending a gunicorn subprocess harness (`GunicornHarness`). These tests are the **authoritative pre-deploy fork-safety signal** per `ci-gates.md`.

**Required before production deploy**: un-stub and green all 14 tests on the nightly CI run.

## Stress Test Scope

No dedicated stress test (e.g., `tests/stress/`) was authored for this change. Rationale:
- This change reduces Oracle load at startup (N×prewarm → 1×prewarm); it does not add new request-path load.
- Concurrent request stress behavior (no shared-connection cross-talk) is covered by AC-2 in the multi-worker integration tests.
- Per test-layer governance (`project_test_layer_governance.md`): stress is not pre-merge.

## Conditions for Production Clearance

1. **First-restart verification** — after deploy, confirm in `error.log`:
   - Each prewarm task appears exactly once (not N times): downtime_analysis, material_consumption, resource_history DuckDB, resource_cache `init_cache()`
   - No "Resource cache version changed: X -> X" followed by Oracle load
   - No "timed out waiting for peer worker" from resource_history_duckdb_cache
   - No ORA-3135 / ORA-1012 connection errors in the first 10 minutes
   - All expected background thread names appear in each worker PID's log

2. **Nightly CI gate** — Tier 3 `nightly-integration` must pass with all 14 multi-worker fork-safety tests green (requires implementing `GunicornHarness` subprocess fixture).

3. **Rollback ready** — one-line revert: comment out `preload_app = True` in `gunicorn.conf.py` and redeploy. No parquet cleanup, no migration rollback, no env var change needed.

## Risk Residuals

| risk | mitigation | owner |
|---|---|---|
| `post_fork` step fails silently | each step wrapped in try/except; failures log warning only | ops team monitors error.log on first restart |
| Master blocks ~25s on prewarm before first worker accepts traffic | acceptable vs N×parallel Oracle load; can be made async-on-master in follow-up | future change |
| 14 fork-safety tests are stubs | must be un-stubbed before production (see condition 2 above) | backend-engineer follow-up |
| `_APP_INSTANCE` module-level var not thread-safe for concurrent `create_app()` | not a real scenario in gunicorn; single-threaded master `create_app()` | no action needed |
