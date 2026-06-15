---
change-id: fix-e2e-spec-failures
schema-version: 0.1.0
last-changed: 2026-06-15
risk: low
tier: 4
---

# Test Plan: fix-e2e-spec-failures

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 (Group A – submit button selector) | e2e | frontend/tests/playwright/production-history-multi-line-input.spec.ts | 1 |
| AC-1 (Group A – submit button selector) | e2e | frontend/tests/playwright/production-history-wildcard-paste.spec.ts | 1 |
| AC-2 (Group B – sidebar open before nav) | e2e | frontend/tests/playwright/job-abandon-on-unload.spec.js | 1 |
| AC-2 (Group B – back/forward resilience) | resilience | frontend/tests/playwright/resilience/browser-history.spec.js | 1 |
| AC-3 (Group C – async 202 auth + SPA nav) | e2e | frontend/tests/playwright/hold-history-flat-table.spec.js | 1 |
| AC-4 (Group D – matrix container selector) | e2e | frontend/tests/playwright/wip-matrix-drilldown.spec.js | 1 |
| AC-5 (Group E – waitForResponse ordering) | e2e | frontend/tests/playwright/production-history-pruning-feedback.spec.ts | 1 |
| AC-6 (Group F – reject-history API mocks) | e2e | frontend/tests/playwright/reject-history.spec.js | 1 |
| AC-6 (Group F – reject material mocks) | e2e | frontend/tests/playwright/reject-material-flat-table.spec.js | 1 |
| AC-7 (full suite 126/0/7) | e2e | frontend/tests/playwright/ | 1 |
| AC-8 (no production-source edits) | static | frontend/tests/playwright/ | 0 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| e2e | 1 | All 9 spec files; Playwright with route mocks; no Oracle dependency |
| resilience | 1 | browser-history.spec.js back/forward path; inline sidebar toggle (not navigateViaSidebar) |
| static | 0 | Git diff confirms zero edits outside frontend/tests/playwright/; verify via CI path filter |

## Test Execution Ladder

| phase | required | command source | max failures | result artifact |
|---|---:|---|---:|---|
| collect | yes | `cd frontend && npx playwright test --list` | 0 | confirms 9 files + 3 pre-existing skips visible |
| targeted | yes | `cd frontend && npx playwright test production-history-multi-line-input.spec.ts production-history-wildcard-paste.spec.ts job-abandon-on-unload.spec.js resilience/browser-history.spec.js hold-history-flat-table.spec.js wip-matrix-drilldown.spec.js production-history-pruning-feedback.spec.ts reject-history.spec.js reject-material-flat-table.spec.js` | 0 | test-evidence.yml |
| changed-area | yes | same as targeted (all edits are within these 9 files) | 0 | test-evidence.yml |
| full | yes | `cd frontend && npm run test:e2e` | 0 | 126 passed / 0 failed / 7 skipped |

## Test Update Contract

All 9 spec files are being repaired, not behaviorally changed. No existing passing test is being deleted or downgraded.

| existing test | action | reason |
|---|---|---|
| hold-history-flat-table.spec.js – async 202 describe (3 tests) | fix | hash-URL goto bypassed auth; replace with loginViaApi + navigateViaSidebar |
| reject-history.spec.js – all tests | fix | Oracle dependency removed by adding page.route mocks |
| reject-material-flat-table.spec.js – all tests | fix | same as above; add material-trace mocks |
| production-history-*.spec.ts – submit button tests | fix | selector retarget to data-testid |
| job-abandon-on-unload.spec.js | fix | sidebar must be open before sidebar-link click |
| resilience/browser-history.spec.js – back/forward test | fix | sidebar open inline (not navigateViaSidebar; goBack must not see extra history entry) |
| wip-matrix-drilldown.spec.js | fix | waitForSelector: table → .matrix-container (table is data-gated) |
| production-history-pruning-feedback.spec.ts | fix | register waitForResponse before navigateViaSidebar (mount fires during nav) |

## Test-Discipline Constraints

Verified by qa-reviewer before gate:

- No assertion weakened: `toBeEnabled`, form-error selectors, `.async-job-progress` visibility, column-presence, download event must all remain.
- No wait lowered to bypass real async behaviour.
- Group F mocks must carry populated `detail.items` rows so column-presence assertions exercise real rendering.
- `browser-history.spec.js` back/forward test must NOT use `navigateViaSidebar` for the second nav.
- No `test.skip()` added to reach green; the 7 skips are: 3 pre-existing intentional skips + 4 wip-matrix-drilldown tests that skip via the pre-existing `if (matrixCell.count() === 0) test.skip()` guard (no Oracle data in mock = no matrix cells = skip, as designed per AC-4).

## Stop Rules

- Do not run full suite before targeted and changed-area phases pass.
- Do not investigate more than the first failure per phase.
- Do not classify any failure as known, pre-existing, waived, or allowed.
- If Group F mock shape cannot be derived from route + App.vue consumer, raise CER-003 rather than guessing field names.

## Out of Scope

- Unit, contract, integration, visual, stress, soak, and monkey test families.
- Changes to `_auth.js`, production source, contracts, CSS, env, or CI workflow files.
- Refactoring passing specs or renaming helpers.

## Notes

All 9 spec files are simultaneously the deliverable and the proof artifact. AC-7 (126/0/7) is the binding exit gate; AC-1..AC-6 are intermediate checkpoints per repair group. 7 skips = 3 pre-existing + 4 wip-matrix test.skip guards firing (no Oracle data in WIP mock → no matrix cells → skip via existing guard). Count must not grow beyond 7.
