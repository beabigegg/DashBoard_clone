# CI/CD Gate Plan — production-achievement-kanban

## Change ID
production-achievement-kanban

## Required Gates for This Change
| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|---:|---|---|---|
| contract-validate | 0 | yes | local pre-PR | `cdd-kit validate` | — |
| lint | 0 | yes | local / PR | `ruff check .` | — |
| response-shape-validate | 1 | yes | push / PR | `cdd-kit validate --contracts` | — (asserts new endpoint samples in `tests/contract/response-samples.json`, incl. `PUT /api/production-achievement/targets` 403 sample, per test-plan.md contract row) |
| unit-mock-integration | 1 | yes | PR | `pytest -m "not (e2e or integration_real or stress or load or soak or multi_worker)" --ignore=tests/integration --ignore=tests/stress --ignore=tests/e2e --ignore=tests/manual -x` | junit XML |
| frontend-unit | 1 | yes | PR | `cd frontend && npm run test` | vitest report |
| css-governance | 1 | yes | PR | `cd frontend && npm run css:check` | governance report (`.theme-production-achievement` scoping, Rule 6) |
| playwright-critical-journeys | 1 | yes | PR | `cd frontend && npx playwright test tests/playwright/hold-overview.spec.js tests/playwright/reject-history.spec.js tests/playwright/query-tool.spec.js tests/playwright/eap-alarm.spec.js tests/playwright/production-achievement.spec.js` | playwright trace |
| playwright-resilience | 1 | yes | PR | `cd frontend && npx playwright test tests/playwright/resilience/` | playwright trace (MySQL-unavailable / `MYSQL_OPS_ENABLED=false` degrade-safe cases, test-plan.md resilience row) |
| playwright-data-boundary | 1 | yes | PR | `cd frontend && npx playwright test tests/playwright/data-boundary/` | playwright trace (negative/non-numeric `target_qty`, unmapped SPECNAME, empty result, test-plan.md data-boundary row) |
| visual-regression | 2 | informational | PR | (TBD — Playwright screenshot diff) | screenshot diff |
| nightly-integration | 3 | yes (nightly) | schedule / dispatch | `pytest tests/integration/ --run-integration-real -m "integration_real or multi_worker" -x` | test report (picks up `tests/integration/test_production_achievement_mysql_roundtrip.py` and `tests/integration/test_production_achievement_filter_cache_reuse.py`, test-plan.md integration row) |
| stress-load / soak | 4 | not applicable | weekly/manual | — | — |

Test IDs are enumerated in `test-plan.md` §Test File / Case Index and §Acceptance Criteria → Test Mapping; this table only asserts which existing gate command each family lands in.

**Tier 4 (stress/soak) explicitly does not apply.** Confirmed non-goal (change-request.md,
change-classification.md, test-plan.md §Out of Scope): not an auto-refresh/big-screen kanban,
no new queue/worker/long-running surface, no new high-load path. `stress-load`/`soak` are not
extended; no `stress-soak-report.md` required.

## workflow

No new gate tier, job ID, or workflow YAML file is introduced. The only registered CI
workflow edit is the one already made in `contracts/ci/ci-gate-contract.md` (schema-version
1.3.35): `tests/playwright/production-achievement.spec.js` appended to the
`playwright-critical-journeys` command (Gate Inventory row above). All other new tests (unit
shift_code/output_date/service/target/permission modules, contract response samples,
resilience/data-boundary specs, MySQL round-trip + filter-cache-reuse integration tests) are
auto-discovered by the existing `unit-mock-integration`, `response-shape-validate`,
`playwright-resilience`, `playwright-data-boundary`, and `nightly-integration` gate commands —
no marker changes, no new `--ignore` path, no new job.

Confirmation: the ci-gate-contract.md "production-achievement-kanban Gate Compatibility Note"
(schema-version 1.3.35) is complete and correct against test-plan.md — every test family row
(unit, contract, integration, e2e, data-boundary, resilience) maps to an existing gate command
with no gaps, and correctly states no new tier/command/workflow file is needed.

**Manual deploy preconditions (not gate-enforced):** applying
`scripts/sql/production_achievement_tables.sql` and setting `MYSQL_OPS_ENABLED=true` in
production (design.md §Migration/Rollback; env-contract.md §MySQL OPS) are operator actions —
no automated check can verify a human ran a DDL script or flipped a prod env var. These are
promotion-policy/deploy-checklist items, not CI gates, and MUST NOT block merge eligibility.
Manifest/nav entries (`asset_readiness_manifest.json`, `route_scope_matrix.json`,
`navigationManifest.js`) ARE code changes and fall under normal PR review (ci-gate-contract.md
deploy checklist items 1–3).

## promotion policy

**Blocking (must pass before merge):** `contract-validate`, `lint` (Tier 0);
`response-shape-validate`, `unit-mock-integration`, `frontend-unit`, `css-governance`,
`playwright-critical-journeys`, `playwright-resilience`, `playwright-data-boundary` (Tier 1);
Test Execution Ladder per test-plan.md (collect → targeted → changed-area → contract →
full, max 1 failure per phase per Stop Rules); `business-rules.md` PA-01..PA-07 entries present
(AC-8, contract-reviewer check, part of `contract-validate`).

**Tracked, non-blocking:** `visual-regression` (Tier 2, informational) — evidence via
`agent-log/visual-reviewer.yml`; promotes per `ci-gate-contract.md §Informational Gate
Promotion Policy` (20 days / 60 runs / pass-rate threshold / runtime limit / owner assigned),
no accelerated promotion requested. `nightly-integration` (Tier 3) — required nightly, not
required for this PR's merge; failure triaged within 1 business day.

**Not a gate at all:** the manual deploy preconditions above (DDL script, `MYSQL_OPS_ENABLED`)
are production-activation checklist items, tracked outside CI, never merge-blocking.

## rollback policy

Reference `design.md §Migration / Rollback` and `ci-gate-contract.md`
"production-achievement-kanban Gate Compatibility Note → Rollback checklist" for full steps
(remove manifest/nav entries; no Oracle spool cleanup — no DuckDB spool used; two new MySQL
tables left in place, not dropped, orphaned-but-harmless; no RQ worker to stop). No
gate-specific rollback beyond reverting the one spec-list line added to
`playwright-critical-journeys` if the page is rolled back. Standard rule applies
(`ci-gate-contract.md §Rollback Policy`): any Tier 1 gate turning red blocks new PRs to main
until fixed; Tier 3 failure requires an incident ticket within 24 hours.

## Merge Eligibility

mergeable when all Tier 1 required gates above pass and the Test Execution Ladder
(test-plan.md) completes with no unresolved failures. `visual-regression` is
informational-risk only. The manual deploy checklist (DDL script, `MYSQL_OPS_ENABLED=true`)
is a post-merge production-activation precondition and does not affect merge eligibility.
