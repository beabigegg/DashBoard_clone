# CI/CD Gate Plan

## Change ID
production-achievement-async-spool

## Required Gates
| gate | tier | required | trigger | command/workflow | expected artifact |
|---|---:|---:|---|---|---|
| contract-validate | 0/1 | yes | local pre-PR / PR | `cdd-kit validate` + `cdd-kit validate --contracts` (`contract-driven-gates.yml`) | — |
| unit-mock-integration | 1 | yes | PR (`backend-tests.yml`) | `pytest tests/ --ignore=tests/e2e --ignore=tests/stress` — auto-discovers `test_production_achievement_unified_job.py`, `_APPROVED_CALLERS` (AC-4), job-registry count, `spool_routes._ALLOWED_NAMESPACES` param (AC-3), env default/enum (AC-5) | junit XML |
| worker-env-parity-static | 1 | yes | PR (`backend-tests.yml`, new step) | greps `deploy/*.service` for a hardcoded `*_USE_UNIFIED_JOB`/`*_USE_RQ` `Environment=` override; parity comes only from the shared `EnvironmentFile=-/opt/mes-dashboard/.env` (AC-5, load-bearing — see Workflow Changes) | shell output |
| dual-tier-parity (Node) | 1 | yes | PR (`backend-tests.yml`, existing Node 22 setup) | Node-subprocess parity test diffing DuckDB-WASM output vs `build_achievement_rows()` golden via `tests/fixtures/frontend_compute_parity.json` (AC-7) — auto-discovered, no workflow change | junit XML |
| frontend-unit | 1 | yes | PR (`frontend-tests.yml`) | `npm test` — new `useProductionAchievementDuckDB` rollup/target-join/rate unit tests (AC-7) | vitest report |
| frontend-type-check | 1 | informational | PR | `npm run type-check` (`continue-on-error: true`, unchanged policy) | — |
| css-governance | 1 | yes | PR | `npm run css:check` (no new tokens; still enforced) | governance report |
| production-achievement-async-e2e | 1 | yes | PR (`frontend-tests.yml`, new step) | `npx playwright test tests/playwright/production-achievement-async.spec.ts` (chromium already installed by the existing shared step) — AC-1, AC-2, AC-7, AC-8 | playwright trace |
| playwright-critical-journeys | 1 | yes | PR (existing) | existing command; `tests/playwright/production-achievement.spec.js` report-render assertions must be updated for the new job/poll/spool contract in the same PR — filter/admin-permission/target-edit assertions are unaffected (non-goal) | playwright trace |
| playwright-resilience | 1 | yes | PR (existing) | existing command auto-discovers new specs under `tests/playwright/resilience/` — worker crash, Redis down, job timeout, missing spool (AC-9) | playwright trace |
| playwright-data-boundary | 1 | yes | PR (existing) | existing command auto-discovers new specs under `tests/playwright/data-boundary/` — empty result, missing targets, malformed spool rows | playwright trace |
| nightly-integration | 3 | yes (nightly) | schedule/dispatch (`backend-tests.yml`) | existing `integration_real` command picks up `test_production_achievement_rq_async.py`, filter-cache-reuse, mysql-roundtrip tests | test report |
| stress-load | 4 | required before prod activation | weekly/manual (`stress-tests.yml`) | existing `tests/stress/ -m stress --run-stress`; extend the cross-worker semaphore stress fixture to include the PA worker as a 5th concurrent worker type | perf report |
| soak | 4 | required before prod activation | weekly/manual (`soak-tests.yml`) | existing `test_soak_workload.py --run-integration-real -m soak`, extended with sustained PA job execution | soak report + `stress-soak-report.md` |

## Workflow Changes Applied
- `.github/workflows/backend-tests.yml`: added `deploy/**` to PR/push path triggers; added the `worker-env-parity-static` step (grep-based, runs before Python setup) — fails if any `deploy/*.service` unit hardcodes a `*_USE_UNIFIED_JOB`/`*_USE_RQ` `Environment=` line. This is the concrete, automated form of the "load-bearing" env-parity requirement in `contracts/env/env-contract.md` §Worker Feature-Flag Env-Var Parity: the new worker unit deliberately omits `PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB` and relies solely on the shared `EnvironmentFile=-/opt/mes-dashboard/.env` both gunicorn and the RQ worker load, so a hardcoded override is exactly the failure mode this check catches.
- `.github/workflows/frontend-tests.yml`: added a dedicated `production-achievement-async-e2e` step mirroring the existing `resource-history-async-e2e` step (same async job/poll/spool journey, ADR-0016); no new Playwright-install step needed (already present).
- `deploy/mes-dashboard-production-achievement-worker.service`: new systemd unit, shaped like `mes-dashboard-production-history-worker.service` (`EnvironmentFile`, explicit `PRODUCTION_ACHIEVEMENT_WORKER_QUEUE`/`_JOB_TIMEOUT_SECONDS` env, `src/` on `PYTHONPATH`) plus the `--job-execution-timeout` RQ CLI flag used by the newer `BaseChunkedDuckDBJob` worker units (`wip-worker`, `downtime-worker`, `hold-history-worker`).
- No new workflow *file* and no gate-tier change: all remaining new tests (unit, contract, integration, resilience, data-boundary, stress, soak) fall inside existing gate commands per repo convention (matches `resource-history-rq-async`/`downtime-duckdb-join-migration` precedent).

## Required Check Policy
Tier-1 rows above (`unit-mock-integration`, `worker-env-parity-static`, `dual-tier-parity`, `frontend-unit`, `css-governance`, `production-achievement-async-e2e`, `playwright-critical-journeys`, `playwright-resilience`, `playwright-data-boundary`) block merge, per `ci/gate-policy.md` Tier 1. `frontend-type-check` stays informational (repo-wide policy, unchanged by this change). Tier 3/4 rows do not block PR merge; see Rollback/Merge Eligibility for their production-activation gate.

## Informational Gate Promotion Policy
No new informational gate is introduced by this change — every new gate ships directly as Tier-1 required, matching the `resource-history-rq-async` precedent (same shared async-job pattern already trusted required from day one). `frontend-type-check` remains subject to the repo-wide 20-day/60-run promotion policy in `contracts/ci/ci-gate-contract.md`, unaffected by this change.

## Rollback Policy
- Zero-downtime kill switch: set `PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB=off` in the shared `.env`; restart gunicorn + the worker (module-level constant frozen at boot). No legacy sync path exists — spool-miss then returns 503 (safe pre-launch); spool-hit still serves.
- Hard rollback: revert the atomic PR; `systemctl disable --now mes-dashboard-production-achievement-worker.service`; `rm -f tmp/query_spool/production_achievement/*.parquet`; unregister `_ALLOWED_NAMESPACES`/`_APPROVED_CALLERS` entries in a follow-up PR only if fully reverting (design.md Migration/Rollback).
- Schema-break rollback: any `_PA_SPOOL_SCHEMA_VERSION` bump ships the same `rm -f tmp/query_spool/production_achievement/*.parquet` in the same commit (data-shape-contract.md; cache-spool-patterns.md).

## Artifact Retention
No new artifact types. Reuses `contracts/ci/ci-gate-contract.md` §Artifact Retention Policy: playwright traces 7 days (30 on failure), pytest/vitest reports 30 days, stress/soak reports 90 days.

## Merge Eligibility Decision
mergeable, once (a) all Tier-1 rows above are green, and (b) `stress-soak-report.md` is signed off. Because `PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB` defaults `on` (pure kill switch, no gradual-rollout flag-flip step like sibling `*_USE_UNIFIED_JOB` flags), the stress/soak automated tests stay at their existing Tier-4 weekly/manual-dispatch tier (not PR-blocking, per tier semantics) — but `stress-soak-report.md` sign-off is required *before* `mes-dashboard-production-achievement-worker.service` is started in any environment, since there is no later "flip to on" step to gate on separately. As of this review, implementation (tasks 3.x/4.x) has not landed yet, so this decision documents the policy the eventual PR must satisfy, not a live pass/fail verdict.

## Notes
Test file pointers and AC mapping live in `test-plan.md` / `change-classification.md` §Inferred Acceptance Criteria (AC-1..AC-9) and `context-manifest.md` §Required Tests — not duplicated here.
