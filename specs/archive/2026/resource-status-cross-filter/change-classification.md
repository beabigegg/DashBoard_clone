# Change Classification — resource-status-cross-filter

## Change Types
- primary: `ui-only-change`, `feature-enhancement`
- secondary: `frontend-state-management` (new composable), `css-change` (scoped additions only)

## Risk Level
- medium

## Impact Radius
- module-level: `frontend/src/resource-status/` (5 components + new composable + style.css)

## Tier
- 2

## Architecture Review Required
- yes
- reason: Introduces a new cross-component client-side state pattern (`useCrossFilter.ts`) coordinating 4 chart components with AND/intersection semantics, plus an unresolved data-flow decision on whether to unify existing `matrixFilter[]`/`summaryStatusFilter` into the new orchestrator or keep them parallel. These non-obvious design decisions must be recorded before implementation. Bounded by existing precedent (`useFilterOrchestrator.ts`, yield-alert cross-filter), so a short `design.md` suffices.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts

| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | Captured in change-request Known Context |
| proposal.md | no | Product intent is clear |
| spec.md | no | design.md + implementation-plan cover behavioral scope |
| design.md | **yes** | Architecture Review Required = yes; records intersection semantics, matrixFilter unification, clear-selection UX, ECharts binding |
| qa-report.md | no | Routine evidence in agent-log; escalate only on blocking findings |
| regression-report.md | no | Regression scope bounded; covered via tests + agent-log pointer |
| visual-review-report.md | no | Escalate only if Phase 2 dim-effect pulled into scope |
| monkey-test-report.md | no | Not applicable at Tier 2 |
| stress-soak-report.md | no | Client-side array filtering; no load surface |

## Required Contracts
- API: none (frontend-only; `/api/resource/status` payload unchanged)
- CSS/UI: `contracts/css/css-contract.md` (Rule 6 scoping + Rule 4.4); `contracts/css/css-inventory.md` (conditional — only if new CSS file added)
- Env: none
- Data shape: none
- Business logic: `contracts/business/business-rules.md` — add cross-filter intersection-semantics rule (AND, exclude-self, clear-selection)
- CI/CD: none (unless Playwright spec added later)

## Required Tests
- unit: `useCrossFilter.ts` composable (selection state, AND-intersection reducer, exclude-self, clear/re-click/ESC)
- contract: business-rule assertions; pin exclude-self and "selecting A narrows B" per CLAUDE.md cross-filter discipline
- integration: App-level test that click in one chart narrows the other three
- E2E: skipped (deferred; add Chromium CI step if Playwright spec added later)
- visual: via ui-ux-reviewer agent-log (no separate report unless Phase 2 dim-effect added)
- data-boundary: n/a
- resilience: n/a
- fuzz/monkey: n/a
- stress: n/a
- soak: n/a

## Required Agents
(in order)
1. `spec-architect` — design.md: intersection semantics, matrixFilter unification, clear-selection UX, ECharts binding, Phase 2 scope
2. `test-strategist` — writes test-plan.md; maps ACs to test families
3. `ci-cd-gatekeeper` — writes ci-gates.md
4. `implementation-planner` — writes implementation-plan.md after design + tests + CI are known
5. `frontend-engineer` — implements useCrossFilter.ts + wires 4 chart components + App.vue + CSS
6. `contract-reviewer` — verifies business-rules + css-contract + css:check Rule 6
7. `ui-ux-reviewer` — selection highlight, dimmed affordance, ESC focus return
8. `qa-reviewer` — release readiness; regression on matrixFilter/summaryStatusFilter/FilterBar

## Inferred Acceptance Criteria
- AC-1: Clicking an element in any of the 4 charts (Ring segment, Heatmap cell, Matrix row, Alert item) filters all other charts and EquipmentGrid to the matching equipment subset.
- AC-2: When two or more charts have active selections, the displayed subset is the AND-intersection of all active selections (e.g., Ring=UDT ∧ Heatmap=QFP shows only QFP equipment in UDT state).
- AC-3: Each chart's own selectable option set still shows all values for that dimension (exclude-self property).
- AC-4: A selection can be cleared via re-click or ESC; clearing removes that dimension from the intersection.
- AC-5: The existing top FilterBar (`useFilterOrchestrator`) behavior is unchanged and composes correctly with cross-filter selections.
- AC-6: The existing `matrixFilter[]` / `summaryStatusFilter` behavior is either unified into the new orchestrator (per design decision) or remains functional in parallel with no regression.
- AC-7: All new/changed styles are scoped under `.theme-resource-status` and `npm run css:check` Rule 6 passes with zero unscoped top-level rules.
- AC-8: Selected elements have a clear visual highlight; keyboard ESC clears the selection and returns focus to the clicked element.

## Tasks Not Applicable
- not-applicable: 2.1, 2.3, 2.4, 2.6, 3.3, 3.4, 3.5, 4.1, 4.3, 4.4, 5.2

## Clarifications or Assumptions
- Assumption: no new authored CSS source file; styles extend existing `style.css`, so `css-inventory.md` update is conditional.
- Assumption: `/api/resource/status` payload unchanged — purely client-side.
- Open question for spec-architect: confirm AND-intersection vs single-active-selection.
- Open question for spec-architect: matrixFilter unification vs parallel — drives regression scope.
- Phase 2 dim effect: out of scope unless spec-architect explicitly pulls it in.

## Context Manifest Draft

### Affected Surfaces
- `frontend/src/resource-status/` (App.vue + 5 chart/grid components + new composable + style.css)
- `contracts/business/business-rules.md`, `contracts/css/css-contract.md`
- `frontend/tests/` (resource-status unit/integration)

### Allowed Paths
- specs/changes/resource-status-cross-filter/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/resource-status/
- frontend/src/shared-composables/useFilterOrchestrator.ts
- frontend/src/shared-composables/index.ts
- frontend/src/shared-ui/components/
- contracts/business/business-rules.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/CHANGELOG.md
- frontend/tests/legacy/resource-status.test.js
- frontend/tests/yield-alert/
- frontend/tests/playwright/production-history-cross-filter.spec.ts
- frontend/scripts/css-governance-check.js
- .github/workflows/frontend-tests.yml

### Agent Work Packets

#### spec-architect
- specs/changes/resource-status-cross-filter/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/resource-status/
- frontend/src/shared-composables/useFilterOrchestrator.ts
- frontend/tests/yield-alert/

#### test-strategist
- specs/changes/resource-status-cross-filter/
- frontend/src/resource-status/
- frontend/tests/legacy/resource-status.test.js
- frontend/tests/yield-alert/
- frontend/tests/playwright/production-history-cross-filter.spec.ts

#### ci-cd-gatekeeper
- specs/changes/resource-status-cross-filter/
- contracts/ci/ci-gate-contract.md
- .github/workflows/frontend-tests.yml
- .github/workflows/contract-driven-gates.yml

#### implementation-planner
- specs/changes/resource-status-cross-filter/
- frontend/src/resource-status/
- contracts/business/business-rules.md
- contracts/css/css-contract.md

#### frontend-engineer
- specs/changes/resource-status-cross-filter/
- frontend/src/resource-status/
- frontend/src/shared-composables/useFilterOrchestrator.ts
- frontend/src/shared-ui/components/
- frontend/tests/legacy/resource-status.test.js
- frontend/tests/yield-alert/
- contracts/business/business-rules.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/CHANGELOG.md
- frontend/scripts/css-governance-check.js
- .github/workflows/frontend-tests.yml

#### contract-reviewer
- specs/changes/resource-status-cross-filter/
- contracts/business/business-rules.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/CHANGELOG.md

#### ui-ux-reviewer
- specs/changes/resource-status-cross-filter/
- frontend/src/resource-status/
- contracts/css/css-contract.md

#### qa-reviewer
- specs/changes/resource-status-cross-filter/
- frontend/src/resource-status/
- frontend/tests/
