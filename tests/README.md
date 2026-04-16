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
