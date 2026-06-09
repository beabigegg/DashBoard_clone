# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- `frontend/src/resource-status/` (App.vue + 5 chart/grid components + new composable + style.css)
- `contracts/business/business-rules.md`, `contracts/css/css-contract.md`
- `frontend/tests/` (resource-status unit/integration)

## Allowed Paths
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
- .github/workflows/contract-driven-gates.yml
- contracts/ci/ci-gate-contract.md

## Required Contracts
- contracts/business/business-rules.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md (conditional — only if new authored CSS file added)

## Required Tests
- frontend/tests/legacy/resource-status.test.js (existing — must not regress)
- New: frontend/tests/resource-status/useCrossFilter.test.ts
- New: frontend/tests/resource-status/App.cross-filter.test.ts

## Agent Work Packets

### spec-architect
- specs/changes/resource-status-cross-filter/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/resource-status/
- frontend/src/shared-composables/useFilterOrchestrator.ts
- frontend/tests/yield-alert/

### test-strategist
- specs/changes/resource-status-cross-filter/
- frontend/src/resource-status/
- frontend/tests/legacy/resource-status.test.js
- frontend/tests/yield-alert/
- frontend/tests/playwright/production-history-cross-filter.spec.ts

### ci-cd-gatekeeper
- specs/changes/resource-status-cross-filter/
- contracts/ci/ci-gate-contract.md
- .github/workflows/frontend-tests.yml
- .github/workflows/contract-driven-gates.yml

### implementation-planner
- specs/changes/resource-status-cross-filter/
- frontend/src/resource-status/
- contracts/business/business-rules.md
- contracts/css/css-contract.md

### frontend-engineer
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

### contract-reviewer
- specs/changes/resource-status-cross-filter/
- contracts/business/business-rules.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/CHANGELOG.md

### ui-ux-reviewer
- specs/changes/resource-status-cross-filter/
- frontend/src/resource-status/
- contracts/css/css-contract.md

### qa-reviewer
- specs/changes/resource-status-cross-filter/
- frontend/src/resource-status/
- frontend/tests/

## Context Expansion Requests
-

## Approved Expansions
-
