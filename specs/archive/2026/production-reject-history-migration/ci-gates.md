# CI/CD Gate Plan

## Change ID
production-reject-history-migration

## Required Gates

| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|---:|---|---|---|
| lint | 0 | yes | local/PR | `ruff check .` | — |
| contract-validate | 0 | yes | local/PR | `cdd-kit validate` | — |
| response-shape-validate | 1 | yes | push/PR | `cdd-kit validate --contracts` (`.github/workflows/contract-driven-gates.yml`) | — |
| unit-mock-integration | 1 | yes | push/PR | `pytest -m "not (e2e or integration_real or stress or load or soak or multi_worker)" --ignore=tests/integration --ignore=tests/stress --ignore=tests/e2e --ignore=tests/manual -x` (`.github/workflows/backend-tests.yml`) | junit XML |
| cdd-kit-gate | 1 | yes | push/PR | `cdd-kit gate production-reject-history-migration` (`.github/workflows/contract-driven-gates.yml`) | — |
| released-pages-hardening | 1 | yes | push/PR | `.github/workflows/released-pages-hardening-gates.yml` | hardening report |
| playwright-resilience | 1 | yes | PR | `cd frontend && npx playwright test tests/playwright/resilience/` (`.github/workflows/e2e-tests.yml`) | playwright trace |
| playwright-critical-journeys | 1 | yes | PR | `cd frontend && npx playwright test tests/playwright/reject-history.spec.js` (`.github/workflows/e2e-tests.yml`) | playwright trace |
| nightly-integration | 3 | yes (nightly) | schedule/dispatch | `pytest tests/integration/ --run-integration-real -m "integration_real or multi_worker" -x` (`.github/workflows/e2e-tests.yml`) | test report |
| stress-load | 4 | yes (weekly) | schedule/dispatch | `pytest tests/stress/ -m "stress or load"` (`.github/workflows/stress-tests.yml`) | perf report |
| soak | 4 | yes (weekly) | schedule/dispatch | `pytest tests/integration/test_soak_workload.py --run-integration-real -m "soak"` (`.github/workflows/soak-tests.yml`) | soak report |

## Workflow Changes

No new workflow files are required. This change follows the P1 precedent (`eap-alarm-unified-job-poc`): all new test files (`tests/test_production_history_worker.py`, `tests/test_reject_history_worker.py`, `tests/integration/test_production_history_rq_async.py`, `tests/integration/test_reject_history_rq_async.py`, `tests/stress/test_production_history_stress.py`, `tests/stress/test_reject_history_stress.py`, `tests/e2e/test_production_history_e2e.py`, `tests/e2e/test_reject_history_e2e.py`) are picked up automatically by existing gate commands.

Feature flags `PRODUCTION_HISTORY_USE_UNIFIED_JOB=off` and `REJECT_HISTORY_USE_UNIFIED_JOB=off` (default) mean zero behavioral change under all gate runs until a flag is explicitly set to `on`.

**Open question (does not block PR merge):** production history may require a new systemd unit (`mes-dashboard-production-history-worker.service`). If added, include it in `deploy/` and reference the unit name in the deploy checklist below. Reject history reuses the existing `deploy/mes-dashboard-reject-worker.service`.

## Promotion Policy

1. Merge to `main` is allowed with both flags off (flag-gated additive code).
2. Promote `PRODUCTION_HISTORY_USE_UNIFIED_JOB=on` in production only after:
   - Tier 1 `unit-mock-integration` green on the PR.
   - Tier 3 `nightly-integration` passes at least one full run under flag=on (set via CI dispatch env override).
   - Tier 4 `stress-load` passes under flag=on in a manual dispatch run.
3. Promote `REJECT_HISTORY_USE_UNIFIED_JOB=on` independently after the same criteria, following the production-history domain promotion (not before).
4. No spool schema changes ship with this PR; promotion does not require parquet cleanup.

## Rollback Policy

**Instant rollback (preferred):**
- Set `PRODUCTION_HISTORY_USE_UNIFIED_JOB=off` and/or `REJECT_HISTORY_USE_UNIFIED_JOB=off` in the environment.
- **Restart** gunicorn and the respective worker(s) — feature flags are module-level constants frozen at boot; `kill -HUP` reloads workers but does NOT propagate env-var changes from master, so a full restart is required.
- No parquet spool cleanup needed: spool schema is unchanged between unified-job and legacy paths.

**Hard rollback (code revert):**
- Revert the PR commit; redeploy.
- If the production-history worker systemd unit was added: stop and disable it before gunicorn restart.
- If the reject-history worker systemd unit registration changed: restore `deploy/mes-dashboard-reject-worker.service` from the previous commit.

Per `ci-gate-contract.md §Rollback Policy`: any Tier 1 gate going red blocks further merges to `main` until fixed.

## Deploy Checklist

1. Verify both flags default to `off` in the deployed environment (`env-contract.md ASYNC-07 / ASYNC-08`).
2. Reject worker: confirm `mes-dashboard-reject-worker.service` registers `RejectHistoryJob` (no new unit needed unless queue isolation is required — see open question above).
3. Production history worker: if a new systemd unit is added, enable and start it; verify queue appears in Admin Dashboard.
4. `rq_monitor_service._QUEUE_NAMES` must include the production-history queue name (only applies if a dedicated queue is configured).

## Merge Eligibility

Mergeable when Tier 1 gates (unit-mock-integration, contract-driven-gates, released-pages-hardening-gates) are green with both flags off. Tier 3/4 gate runs are informational at merge time; flag promotion to `on` is blocked until Tier 3 and Tier 4 pass under flag-on dispatch.
