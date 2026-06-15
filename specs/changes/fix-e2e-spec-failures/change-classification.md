# Change Classification

## Change Types
- primary: bug-fix (test-failure)
- secondary: test-only-change

## Lane
- bug-fix

## Bug Symptom Type
- test-failure

## Diagnostic Only
- no

## Risk Level
- low

## Impact Radius
- isolated

## Tier
- 4

## Architecture Review Required
- no

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | |
| proposal.md | no | |
| spec.md | no | |
| design.md | no | no architecture/design decision; pure test-spec repair |
| qa-report.md | no | pass/fail summary fits in agent-log/*.yml |
| regression-report.md | no | regression evidence is the suite going green |
| visual-review-report.md | no | no UI/visual output change |
| monkey-test-report.md | no | |
| stress-soak-report.md | no | |

## Required Contracts
- API: none (mocks emulate existing documented API responses; no contract change)
- CSS/UI: none
- Env: none
- Data shape: none
- Business logic: none
- CI/CD: none (no workflow edits; edits are to existing spec files only)

## Required Tests
- unit: none
- contract: none
- integration: none
- E2E: all 9 affected spec files must pass; full suite must reach 130 passed / 0 failed / 3 skipped
- visual: none
- data-boundary: none
- resilience: resilience/browser-history.spec.js (Group B) must pass
- fuzz/monkey: none
- stress: none
- soak: none

## Required Agents
- implementation-planner — sequences 6 root-cause groups into ordered execution packet
- bug-fix-engineer — records structured repair evidence in agent-log/bug-fix-engineer.yml; performs fixes
- e2e-resilience-engineer — verifies mock conversion completeness and resilience patterns for Group F
- test-strategist — writes test-plan.md; confirms fixes strengthen (not weaken) assertions
- ci-cd-gatekeeper — writes ci-gates.md
- qa-reviewer — release readiness: confirms full suite green, no spec weakened to pass

## Inferred Acceptance Criteria
- AC-1: Group A (5 tests) — production-history specs target submit button via `[data-testid="ph-query-btn"]`; mixed-CRLF parse and empty-identifier-blocked tests pass
- AC-2: Group B (2 tests) — job-abandon and browser-history specs open sidebar before clicking sidebar links; tests pass
- AC-3: Group C (2 tests) — hold-history 202 async tests authenticate via `loginViaApi` and navigate via `navigateViaSidebar`; `.async-job-progress` appears and tests pass
- AC-4: Group D (4 tests) — wip-matrix-drilldown `waitForSelector` resolves with WIP data mock or correct selector; tests either pass or auto-skip via existing `test.skip` guard
- AC-5: Group E (1 test) — pruning-feedback spec registers `waitForResponse(filter-options)` before navigation; pruned notice appears and auto-clears; test passes
- AC-6: Group F (7 tests) — reject-history and reject-material-flat-table specs run fully against API mocks matching documented response shape; no Oracle dependency; tests pass
- AC-7: Full Playwright suite reports 130 passed / 0 failed / 3 skipped (3 skipped = pre-existing intentional skips); no spec weakened/skipped to achieve green
- AC-8: Zero production-source, contract, CSS, env, or CI-workflow files modified; all edits confined to frontend/tests/playwright/

## Tasks Not Applicable
- not-applicable: 1.3

## Clarifications or Assumptions
- Group F mocks emulate EXISTING documented reject-history API behavior; if engineer finds undocumented shape, stop and raise CER-002 rather than baking assumption into mock
- "blocks CI green" describes priority; no CI workflow change needed (edits are to existing spec files only)
- All Groups B/C reuse existing `loginViaApi` / `navigateViaSidebar` helpers; additive only, no rewrite of _auth.js
- Fixes must not weaken assertions or relax waits merely to make tests pass (test-discipline rules apply)

## Context Manifest Draft

### Affected Surfaces
- Playwright E2E test layer (frontend/tests/playwright/)
- Shared auth/navigation helpers (_auth.js)

### Allowed Paths
- specs/changes/fix-e2e-spec-failures/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/tests/playwright/
- frontend/playwright.config.js
- frontend/src/production-history/App.vue
- frontend/src/portal-shell/App.vue
- frontend/src/portal-shell/sidebarState.js
- frontend/src/wip-overview/
- frontend/src/reject-history/
- src/mes_dashboard/routes/reject_history_routes.py

### Agent Work Packets

#### implementation-planner
- specs/changes/fix-e2e-spec-failures/
- frontend/tests/playwright/

#### bug-fix-engineer
- specs/changes/fix-e2e-spec-failures/
- frontend/tests/playwright/
- frontend/src/production-history/App.vue
- frontend/src/portal-shell/App.vue
- frontend/src/wip-overview/
- frontend/src/reject-history/
- src/mes_dashboard/routes/reject_history_routes.py

#### e2e-resilience-engineer
- specs/changes/fix-e2e-spec-failures/
- frontend/tests/playwright/
- frontend/src/reject-history/
- src/mes_dashboard/routes/reject_history_routes.py

#### test-strategist
- specs/changes/fix-e2e-spec-failures/
- frontend/tests/playwright/

#### ci-cd-gatekeeper
- specs/changes/fix-e2e-spec-failures/
- frontend/playwright.config.js

#### qa-reviewer
- specs/changes/fix-e2e-spec-failures/
- frontend/tests/playwright/
