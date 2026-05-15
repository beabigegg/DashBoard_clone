# Change Classification

## Change Types
- primary: ui-refactor
- secondary: bug-fix (presentation regression vs. intended design pattern)

## Risk Level
- low

## Impact Radius
- module-level (hold-history app + hold-overview app only)

## Tier
- 3

## Architecture Review Required
- no
- reason: No new modules, endpoints, data flows, or cross-module dependencies. Isolated presentational refactor of two existing feature apps.

## Required Artifacts
Always required: change-request.md, change-classification.md, test-plan.md, ci-gates.md, tasks.yml
Optional created: current-behavior.md, qa-report.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | yes | Change hinges on precise description of current "table-within-table" DOM/CSS vs. target flat-table; anchors the refactor and visual review |
| proposal.md | no | |
| spec.md | no | |
| design.md | no | |
| qa-report.md | yes | Two user-visible UI surfaces change; QA report records before/after screenshots and test-pass matrix |
| regression-report.md | no | Covered by qa-report.md + existing test suites |

## Required Contracts
- API: no change — payloads are already flat
- CSS/UI: update css-contract.md to specify hold-history Hold/Release 明細 and hold-overview Hold Lot Details render as single flat tables matching hold-detail / wip-detail pattern
- Env: no change
- Data shape: no change
- Business logic: no change
- CI/CD: no change

## Required Tests
- unit: none new (no logic change)
- contract: css-contract assertion if automated
- integration: none
- E2E: update/verify tests/e2e/test_hold_history_e2e.py and tests/e2e/test_hold_overview_e2e.py (selector updates)
- visual: before/after visual review of both pages vs. hold-detail / wip-detail target pattern
- data-boundary: not applicable
- resilience: not applicable
- fuzz/monkey: not applicable
- stress: not applicable
- soak: not applicable

## Required Agents
1. contract-reviewer — verify CSS/UI contract and confirm API payload is already flat; update css-contract.md
2. test-strategist — write test-plan.md
3. frontend-engineer — implement flat-table refactor in hold-history and hold-overview
4. ui-ux-reviewer — review layout / visual consistency with hold-detail / wip-detail
5. visual-reviewer — screenshot comparison
6. ci-cd-gatekeeper — write ci-gates.md
7. qa-reviewer — final release-readiness decision

## Inferred Acceptance Criteria
- AC-1: On the HOLD-HISTORY page, the Hold / Release 明細 section renders as a single flat table (no nested/expandable sub-table, no inner table container), visually consistent with the detail table on the HOLD-DETAIL and WIP-DETAIL pages.
- AC-2: On the HOLD-OVERVIEW page, the Hold Lot Details section renders as a single flat table, visually consistent with HOLD-DETAIL and WIP-DETAIL.
- AC-3: All existing columns, cell formatting (qty/age/hours number formatting, comment tooltips, fallback values), sorting, and pagination continue to work in both refactored tables.
- AC-4: The API payloads for hold-history detail and hold-overview lots are unchanged; no backend code modification is required (verified, not just assumed).
- AC-5: The shared DataTable.vue component is not modified in a way that regresses other consumers; changes are confined to the hold-history and hold-overview apps and their scoped styles.
- AC-6: Existing tests (tests/e2e/test_hold_history_e2e.py, tests/e2e/test_hold_overview_e2e.py, frontend/tests/playwright/hold-overview.spec.js, frontend/tests/validation/useHoldOverview.validation.test.js) pass after any necessary selector updates, and npm run css:check / npm run type-check pass.

## Tasks Not Applicable
- not-applicable: 2.1, 2.3, 2.4, 2.5, 2.6, 3.2, 3.4, 3.5, 4.1, 4.3, 4.4, 6.4

## Clarifications or Assumptions
- Backend API confirmed to return flat row lists — no nested structure. The "table-within-table" is a pure frontend presentation issue (extra wrapper containers + scoped CSS), not a data-structure issue.
- The shared DataTable.vue must not be modified to fix the issue; changes should be in the consuming app templates and scoped styles only.
- "Align with hold-detail / wip-detail pattern" means: same container structure, same DataTable usage without extra inner card wrappers, same CSS treatment.

## Context Manifest Draft

### Affected Surfaces
- frontend-ui: frontend/src/hold-history/ (DetailTable.vue, App.vue), frontend/src/hold-overview/ (App.vue, components/)
- css: scoped styles in above components, frontend/src/hold-history/style.css, frontend/src/hold-overview/style.css
- tests: tests/e2e/test_hold_history_e2e.py, tests/e2e/test_hold_overview_e2e.py, frontend/tests/playwright/hold-overview.spec.js, frontend/tests/validation/useHoldOverview.validation.test.js
- backend-api: read-only verification of src/mes_dashboard/routes/hold_history_routes.py, hold_overview_routes.py, services/hold_history_service.py

### Allowed Paths
- specs/changes/hold-history-detail-flat-table/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/hold-history/
- frontend/src/hold-overview/
- frontend/src/hold-detail/
- frontend/src/wip-detail/
- frontend/src/shared-ui/components/
- frontend/src/styles/
- src/mes_dashboard/routes/
- src/mes_dashboard/services/
- tests/e2e/
- frontend/tests/playwright/
- frontend/tests/validation/
- contracts/

### Agent Work Packets

#### contract-reviewer
- specs/changes/hold-history-detail-flat-table/
- contracts/
- src/mes_dashboard/routes/
- src/mes_dashboard/services/
- frontend/src/hold-history/
- frontend/src/hold-overview/
- frontend/src/hold-detail/
- frontend/src/wip-detail/

#### test-strategist
- specs/changes/hold-history-detail-flat-table/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/hold-history/
- frontend/src/hold-overview/
- frontend/src/hold-detail/
- frontend/src/wip-detail/
- tests/e2e/
- frontend/tests/playwright/
- frontend/tests/validation/
- contracts/

#### frontend-engineer
- specs/changes/hold-history-detail-flat-table/
- frontend/src/hold-history/
- frontend/src/hold-overview/
- frontend/src/hold-detail/
- frontend/src/wip-detail/
- frontend/src/shared-ui/components/
- frontend/src/styles/
- contracts/

#### ui-ux-reviewer
- specs/changes/hold-history-detail-flat-table/
- frontend/src/hold-history/
- frontend/src/hold-overview/
- frontend/src/hold-detail/
- frontend/src/wip-detail/

#### visual-reviewer
- specs/changes/hold-history-detail-flat-table/
- frontend/src/hold-history/
- frontend/src/hold-overview/
- frontend/src/hold-detail/
- frontend/src/wip-detail/

#### ci-cd-gatekeeper
- specs/changes/hold-history-detail-flat-table/
- contracts/ci/

#### qa-reviewer
- specs/changes/hold-history-detail-flat-table/
- frontend/src/hold-history/
- frontend/src/hold-overview/
- tests/e2e/
- frontend/tests/playwright/
- frontend/tests/validation/
- src/mes_dashboard/routes/
- src/mes_dashboard/services/
