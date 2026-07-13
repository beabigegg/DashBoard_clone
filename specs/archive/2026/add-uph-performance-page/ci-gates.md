# CI/CD Gate Review

Change: `add-uph-performance-page` (Tier 1, high-risk, cross-module). Gate authority:
`contracts/ci/ci-gate-contract.md` §"add-uph-performance-page Gate Compatibility Note"
(already written) and §"New RQ Worker Deploy Checklist". This file does not duplicate
test strategy — see `test-plan.md` for the full AC→test mapping.

## Required Gates for This Change
| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|---:|---|---|---|
| lint | 0 | yes | local/PR | `ruff check .` | — |
| unit-mock-integration | 1 | yes | PR | `pytest -m "not (e2e or integration_real or stress or load or soak or multi_worker)" --ignore=tests/integration --ignore=tests/stress --ignore=tests/e2e --ignore=tests/manual -x` — covers `test_uph_performance_sql_builder.py`, `test_uph_performance_unified_job.py`, and the 3 extended tripwires (spool allowlist, job-registry count, `_APPROVED_CALLERS`) per test-plan.md "Test Update Contract" | junit XML |
| frontend-unit / type-check | 1 | yes | PR | `cd frontend && npm run test` + `npm run type-check` | vitest report |
| css-governance | 1 | yes | PR | `cd frontend && npm run css:check` — new `.theme-uph-performance` scope | governance report |
| contract-validate | 1 | yes | PR | `cdd-kit validate --contracts --env --versions` — resolves 6 new endpoint samples + `UPH_PERFORMANCE_USE_UNIFIED_JOB` env pin (AC-7) | — |
| openapi-sync | 1 | yes | PR | `cdd-kit openapi export` diff-clean for both `contracts/openapi.json` and `contracts/api/openapi.json` (schema-version bump already applied per design.md) | — |
| playwright-critical-journeys | 1 | yes | PR | `cd frontend && npx playwright test ... tests/playwright/uph-performance.spec.ts` — see Workflow Changes below | playwright trace |
| playwright-resilience | 1 | yes | PR | `cd frontend && npx playwright test tests/playwright/resilience/` — auto-discovers worker-unavailable/Oracle-fault specs, no edit needed | playwright trace |
| playwright-data-boundary | 1 | yes | PR | `cd frontend && npx playwright test tests/playwright/data-boundary/` — auto-discovers zero-row empty-state spec, no edit needed | playwright trace |
| nightly-integration | 3 | informational (nightly-required) | schedule/dispatch | `pytest tests/integration/ --run-integration-real -m "integration_real or multi_worker" -x` — `test_uph_performance_rq_async.py` round-trip + extended N-way `heavy_query_slot` fixture | test report |
| stress-load | 4 | weekly, activation-blocking | schedule/dispatch | `pytest tests/stress/ -m "stress or load"` — `test_uph_performance_stress.py` (burst, fairness, no-corruption) | perf report |
| soak | 4 | weekly, activation-blocking | schedule/dispatch | `pytest tests/integration/test_soak_workload.py --run-integration-real -m "soak"` — extended workload list | soak report |

## Workflow Changes Applied
Applied (tasks.yml 4.4, closes the qa-reviewer gap):
1. `.github/workflows/frontend-tests.yml`: added a `Run uph-performance e2e spec
   (add-uph-performance-page, Tier 1)` step running
   `npx playwright test tests/playwright/uph-performance.spec.ts`, placed after the
   `mid-section-defect` step, tagged `# ci-gates.md gate: playwright-critical-journeys
   (Tier 1, required)`. Single `.ts`-suffix form (no `.ts || .js` fallback) — the spec is
   new with no legacy `.js` twin, unlike `downtime-analysis.spec.ts`. Chromium install is
   already covered by the existing shared "Install Playwright browsers" step earlier in
   the job.
2. `contracts/ci/ci-gate-contract.md` Gate Inventory row `playwright-critical-journeys`:
   appended `tests/playwright/uph-performance.spec.ts` to the command list (same pattern as
   the `eap-alarm-analysis` and `production-achievement-kanban` CHANGELOG entries — this
   reuses the existing `playwright-critical-journeys` gate name rather than
   `production-achievement-async-spool`'s separate-named-step precedent, matching this
   change's own gate table above). `schema-version` bumped 1.3.38 -> 1.3.39; entry recorded
   in `contracts/CHANGELOG.md` `[ci 1.3.39]` (per "Version entries go only in
   contracts/CHANGELOG.md" convention — the in-file `## CHANGELOG` section inside
   `ci-gate-contract.md` has been superseded by the central changelog since 1.3.36 and is
   not touched here).
No new workflow file, gate tier, or `deploy/*.service`/`scripts/start_server.sh` template change
is required by CI itself — the systemd unit + launcher wiring is an application/deploy artifact
owned by backend-engineer (tasks.yml 4.3), enforced as a Tier 1 unit test per the
"New RQ Worker Deploy Checklist" (no `--job-execution-timeout`, both files updated together),
not as a workflow YAML change.

Known sandbox limitation (not a gate defect): the new step cannot execute end-to-end in this
development sandbox because `npx playwright install --with-deps chromium` cannot complete here
(pre-existing environment gap, unrelated to this change — also blocks the resilience/data-boundary
specs). The step is statically verified consistent with sibling steps (same job, same working
directory, same install-once-run-many pattern) and will execute normally on GitHub-hosted runners
where the Chromium install step succeeds.

## Promotion Policy
Mirrors `production-achievement-async-spool`'s rollout (collapsed sign-off-onto-first-start,
since `UPH_PERFORMANCE_USE_UNIFIED_JOB` defaults `on` with no legacy path):
1. Merge — Tier 1 required gates above green; worker code ships but
   `mes-dashboard-uph-performance-worker.service` is not yet started in any environment.
2. `stress-soak-report.md` sign-off recorded (per classification.md optional-artifact list) —
   mandatory before first start in ANY environment, because this queries a >180s-timeout-history
   table with no legacy fallback (see the pre-written Gate Compatibility Note).
3. Start `mes-dashboard-uph-performance-worker.service`.
4. Verify `rq_monitor_service` / Admin Dashboard Worker Status shows the `uph-performance` queue
   with ≥1 active worker.
5. Done — nightly-integration informational gate promoted to routine-green monitoring; no further
   promotion step (no Tier 2 informational gate exists for this change to graduate from).

## Rollback Policy
Kill switch: `UPH_PERFORMANCE_USE_UNIFIED_JOB=off` — zero-downtime, no legacy path so spool-miss
returns 503 (matches production-achievement precedent). Hard rollback: stop/disable
`mes-dashboard-uph-performance-worker.service` and remove the parquet namespace dir. Full
procedure, restart requirements, and blast-radius reasoning are authoritative in `design.md`
§"Migration / Rollback" — not repeated here.

## Merge Eligibility
mergeable — conditional on all Tier 1 required gates above passing AND
`deploy/mes-dashboard-uph-performance-worker.service` + `scripts/start_server.sh` wiring landing
in the same PR as the worker module (hard requirement, `ci-gate-contract.md` §New RQ Worker
Deploy Checklist). Production activation (systemd unit first start) remains blocked independent
of merge, pending `stress-soak-report.md` sign-off per Promotion Policy above.
