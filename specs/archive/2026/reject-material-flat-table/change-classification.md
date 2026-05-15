# Change Classification

## Change Types
- primary: bug-fix (presentational)
- secondary: css-refactor

## Risk Level
- low

## Impact Radius
- module-level (reject-history, material-trace)

## Tier
- 3

## Architecture Review Required
- no
- reason:

## Required Artifacts
Always required: change-request.md, change-classification.md, test-plan.md, ci-gates.md, tasks.yml

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | |
| proposal.md | no | |
| spec.md | no | |
| design.md | no | |
| qa-report.md | no | |
| regression-report.md | no | |

## Required Contracts
- API: none — no API change
- CSS/UI: contracts/css/css-contract.md — add reject-history and material-trace to Detail Table Layout Rule table
- Env: none
- Data shape: none
- Business logic: none
- CI/CD: none

## Required Tests
- unit: none (pure UI refactor; confirmed by pattern from hold-history-detail-flat-table)
- contract: css:check must pass
- integration: none
- E2E: new Playwright spec for reject-history flat table; update material-trace spec if exists
- visual: visual review of both pages
- data-boundary: none
- resilience: none
- fuzz/monkey: none
- stress: none
- soak: none

## Required Agents
1. contract-reviewer (CSS contract update — add reject-history + material-trace to Detail Table Layout Rule)
2. test-strategist (write test-plan.md)
3. frontend-engineer (CSS padding:0 override for both pages)
4. ui-ux-reviewer (confirm no content outside DataTable is affected)
5. visual-reviewer (confirm DataTable flush layout)
6. ci-cd-gatekeeper (write ci-gates.md)
7. qa-reviewer (release readiness)

## Inferred Acceptance Criteria
AC-1: In `reject-history/components/DetailTable.vue`, the `.card-body` wrapping the Hold/Release detail DataTable carries an override class with `padding: 0` (scoped), so the DataTable sits flush against the card edge with no inner padding frame.
AC-2: In `material-trace/App.vue`, the `.card-body` wrapping the Result detail DataTable carries an override class with `padding: 0` (scoped), so the DataTable sits flush against the card edge with no inner padding frame.
AC-3: `npm run css:check` (CSS governance) continues to pass with 0 errors; the new override classes comply with the CSS contract.
AC-4: `npm run test` (Vitest) continues to pass — 331 tests, 0 regressions.
AC-5: No API endpoint, response shape, data shape, or backend behavior is changed.
AC-6: Other content inside the affected cards (headers, toolbars, filter controls, error banners, etc.) remains visually unaffected — only the DataTable padding frame is removed.

## Tasks Not Applicable
- not-applicable: 2.1, 2.3, 2.4, 2.5, 2.6, 3.1, 3.2, 3.4, 3.5, 4.1, 4.3, 4.4, 6.4

## Clarifications or Assumptions
- Pattern proven by hold-history-detail-flat-table (already shipped and gate-passed).
- `material-trace/App.vue` is a non-migrated JS SFC; fix applies to template/style only — no TS migration in scope.
- css-inventory.md update required if new override classes are added (per CSS contract §7).

## Context Manifest Draft

### Affected Surfaces
- frontend-ui: `frontend/src/reject-history/` (DetailTable.vue, App.vue, style.css), `frontend/src/material-trace/` (App.vue, style.css)
- css: scoped styles in above components

### Allowed Paths
- specs/changes/reject-material-flat-table/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/
- frontend/src/reject-history/
- frontend/src/material-trace/
- frontend/src/hold-history/
- frontend/src/hold-overview/
- frontend/src/hold-detail/
- frontend/src/wip-detail/
- frontend/src/shared-ui/components/
- frontend/src/styles/
- tests/e2e/
- frontend/tests/playwright/

### Agent Work Packets

#### change-classifier
- specs/changes/reject-material-flat-table/
- specs/context/project-map.md
- specs/context/contracts-index.md

#### contract-reviewer
- specs/changes/reject-material-flat-table/
- contracts/
- frontend/src/reject-history/
- frontend/src/material-trace/
- frontend/src/hold-history/
- frontend/src/hold-overview/
- frontend/src/hold-detail/
- frontend/src/wip-detail/

#### test-strategist
- specs/changes/reject-material-flat-table/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/reject-history/
- frontend/src/material-trace/
- frontend/tests/playwright/
- contracts/

#### frontend-engineer
- specs/changes/reject-material-flat-table/
- contracts/css/
- frontend/src/reject-history/
- frontend/src/material-trace/
- frontend/src/hold-history/
- frontend/src/hold-detail/
- frontend/src/wip-detail/
- frontend/src/shared-ui/components/
- frontend/src/styles/

#### ui-ux-reviewer
- specs/changes/reject-material-flat-table/
- frontend/src/reject-history/
- frontend/src/material-trace/
- frontend/src/hold-detail/
- frontend/src/wip-detail/

#### visual-reviewer
- specs/changes/reject-material-flat-table/
- frontend/src/reject-history/
- frontend/src/material-trace/
- frontend/src/hold-detail/
- frontend/src/wip-detail/

#### ci-cd-gatekeeper
- specs/changes/reject-material-flat-table/
- contracts/ci/

#### qa-reviewer
- specs/changes/reject-material-flat-table/
- frontend/src/reject-history/
- frontend/src/material-trace/
- tests/e2e/
- frontend/tests/playwright/
