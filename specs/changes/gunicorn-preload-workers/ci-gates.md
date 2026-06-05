# CI/CD Gate Plan — gunicorn-preload-workers

## Required Gates

| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|---:|---|---|---|
| contract-validate | 0 | yes | local pre-PR | `cdd-kit validate` | pass/fail |
| lint | 0 | yes | local/PR | `ruff check .` | pass/fail |
| type-check | 0 | informational | local/PR | `mypy src/` | pass/fail |
| unit-mock-integration | 1 | yes | pull_request | `pytest -m "not (e2e or integration_real or stress or load or soak or multi_worker)" --ignore=tests/integration --ignore=tests/stress --ignore=tests/e2e --ignore=tests/manual -x` | pass/fail |
| nightly-integration | 3 | yes (pre-deploy) | nightly schedule / workflow_dispatch | `pytest tests/integration/ --run-integration-real -m "integration_real or multi_worker" -x` | pass/fail |
| soak | 4 | yes (weekly) | weekly schedule | soak-tests.yml | soak report |

New test files covered by existing gate commands (no new workflow YAML needed):
- `tests/test_post_fork_reinit.py` — Tier 1, no special marker, covered by `unit-mock-integration`
- `tests/test_resource_cache_version_check.py` — Tier 1, no special marker, covered by `unit-mock-integration`
- `tests/integration/test_preload_fork_safety.py` — Tier 3, markers `integration_real` + `multi_worker`, covered by `nightly-integration`

## CI/CD Workflow

Workflow files involved (no structural changes required — new tests drop into existing commands):

- `.github/workflows/backend-tests.yml` — triggers Tier 1 `unit-mock-integration` on every PR; picks up `test_post_fork_reinit.py` and `test_resource_cache_version_check.py` automatically via the existing pytest glob.
- `.github/workflows/soak-tests.yml` — Tier 4 weekly soak; covers restart-loop and connection-leak verification for the `preload_app` change.
- `.github/workflows/stress-tests.yml` — existing; no changes needed for this change.
- `.github/workflows/measure-stability.yml` — existing; no changes needed.
- `.github/workflows/released-pages-hardening-gates.yml` — existing; no changes needed.

The Tier 3 `nightly-integration` gate already uses `pytest tests/integration/ --run-integration-real -m "integration_real or multi_worker" -x`. `test_preload_fork_safety.py` carries both markers and is automatically included.

No new workflow YAML files are created. No existing workflow job names are changed.

## Promotion Policy

- Tier 0 (`contract-validate`, `lint`): must pass locally before opening a PR.
- Tier 1 (`unit-mock-integration`): must pass on PR before merge. Covers fork-safety unit tests and version-guard tests.
- Tier 3 (`nightly-integration`, `multi_worker`): must pass on the nightly run before production deploy. The `test_preload_fork_safety.py` multi-worker test is the authoritative pre-deploy signal for this change.
- Tier 4 (`soak`): must pass on the weekly run before any soak-sensitive promotion. Restart-loop and connection-leak verification included.
- No staged rollout is required. This change has no user-facing API, UI, data, or business logic surface.

## Rollback Policy

- One-line revert: comment out or remove `preload_app = True` from `gunicorn.conf.py` and redeploy.
- No parquet spool schema change — no `rm tmp/query_spool/...` step required on rollback.
- No database migration — no rollback migration script.
- No new env var introduced (per design.md) — no `.env` cleanup on rollback.
- If a per-worker resource (Oracle pool, Redis client, DuckDB cache) fails to reinit after rollback, restart gunicorn cleanly; the pre-fork model restores baseline behaviour.

## Merge Eligibility

Mergeable when:
- Tier 0 gates pass locally.
- Tier 1 `unit-mock-integration` passes on PR (includes `test_post_fork_reinit.py` and `test_resource_cache_version_check.py`).
- Tier 3 `nightly-integration` passes on the first nightly run after merge before production deploy.
- `type-check` (`mypy src/`) informational — non-blocking for merge, tracked separately.
