# MES Dashboard Test Suite

## Test Tiers

The project uses four distinct test tiers, each with a different scope and run frequency.

| Tier | Directory | Marker | Run flag | When |
|------|-----------|--------|----------|------|
| **Unit** | `tests/test_*.py` | *(none)* | *(default)* | Every commit |
| **Integration** | `tests/test_*.py` | `integration` | `--run-integration` | Pre-merge (requires DB) |
| **E2E (in-process)** | `tests/e2e/` | `e2e` / `local_e2e` | `--run-e2e` | Pre-merge |
| **Real-environment** | `tests/integration/` | `integration_real` | `--run-integration-real` | **Nightly only** |

### Tier 4: Real-environment integration tests

Tests under `tests/integration/` boot **actual subprocesses** (gunicorn workers, Redis) and a real browser (Playwright) to cover scenarios that mocks cannot reproduce:

- **Multi-worker spool round-trip**: two gunicorn workers share a real `QUERY_SPOOL_DIR`; worker A writes a spool file, worker B reads it back.
- **Cross-process lock exclusion**: `try_acquire_lock` exclusion tested across real OS processes (not threads).
- **Redis chaos**: kill/restart a real Redis mid-flight to verify `fail_mode="closed"` and `fail_mode="raise"` semantics.
- **Shared-volume probe**: each worker writes `probe_<pid>.json` on boot; test asserts both PIDs are visible within 30 s.
- **Tab-close abandonment**: Playwright closes a browser tab mid-job and verifies the server marks it `abandoned`.

#### Running tier-4 tests locally

Prerequisites:
- `redis-server` binary on `$PATH` (already required for `test_distributed_lock.py`)
- `gunicorn` available in the conda env (already in `environment.yml`)
- Playwright browsers in `~/.cache/ms-playwright` — **DO NOT run `playwright install`**

```bash
# Run all real-environment integration tests
conda run -n mes-dashboard pytest tests/integration/ --run-integration-real -v

# Run a single file
conda run -n mes-dashboard pytest tests/integration/test_redis_chaos.py --run-integration-real -v
```

#### Default run (pre-merge)

Without the flag, all `integration_real`-marked tests are **skipped**. The session still passes:

```bash
conda run -n mes-dashboard pytest tests/
# → tests/integration/* SKIPPED, rest of suite runs normally
```

#### Nightly CI

The tier-4 tests are intended for a nightly CI job. This is tracked as a follow-up for ops:
> "Add nightly CI job: `pytest tests/integration/ --run-integration-real -v`"

Pre-merge CI stays on tiers 1–3 only.

### Multi-worker concurrency tests (sub-tier of Tier 4)

Tests in `tests/integration/test_multi_worker_concurrency.py` are marked with both `integration_real` and `multi_worker`. They spawn real RQ worker subprocesses and exercise concurrent-access scenarios:

- **Job idempotence**: crash a worker mid-job; verify no duplicate side-effects after re-pickup
- **Export deduplication**: two workers with identical fingerprint → exactly one execution
- **Stale lock recovery**: lock holder crash → TTL-based recovery verified
- **Result race safety**: 100 concurrent write/read rounds, no partial reads
- **Queue fairness**: 30 jobs / 3 workers — every worker processes ≥ 1

#### Running multi-worker tests locally

```bash
conda run -n mes-dashboard pytest -m multi_worker --run-integration-real -v
```

#### Adding a new multi-worker test

1. Add a mock job function to `tests/integration/_multi_worker_jobs.py`.
   - Record side-effects via `_push_effect(r, job_id, "completed")`.
   - For cross-worker synchronisation use `WorkerBarrier` from `_multi_worker_harness.py`.
2. Write the test in `test_multi_worker_concurrency.py`, mark with `@pytest.mark.multi_worker`.
3. Use `MultiWorkerHarness(redis_url, worker_count=N)` as a context manager.
4. Assert on `read_side_effects(r, job_id)`.
