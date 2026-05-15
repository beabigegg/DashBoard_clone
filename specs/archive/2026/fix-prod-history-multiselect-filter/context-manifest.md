# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- production-history feature app
- 共用 filter / multi-select dropdown 元件（若被 production-history 使用）
- 共用 filter orchestrator composable

## Allowed Paths
- specs/changes/fix-prod-history-multiselect-filter/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/production-history/
- frontend/src/shared-ui/
- frontend/src/shared-composables/
- frontend/src/core/
- frontend/tests/validation/
- frontend/tests/legacy/
- frontend/tests/playwright/
- contracts/api/
- contracts/business/
- contracts/css/

## Required Contracts
- contracts/api/api-contract.md（不變更 endpoint，但確認多選後 payload 仍符合）
- contracts/business/business-rules.md（可能新增「filter apply trigger = dropdown 關閉」一條）
- contracts/css/css-contract.md（不新增 token，確認契約未被破壞）

## Required Tests
- frontend/tests/playwright/production-history-cross-filter.spec.ts
- frontend/tests/validation/useProductionHistory.validation.test.js
- frontend/tests/legacy/production-history.test.js

## Agent Work Packets

### change-classifier
- specs/changes/fix-prod-history-multiselect-filter/
- specs/context/project-map.md
- specs/context/contracts-index.md

### contract-reviewer
- contracts/api/
- contracts/business/
- contracts/css/
- specs/changes/fix-prod-history-multiselect-filter/
- specs/context/contracts-index.md

### test-strategist
- frontend/tests/validation/
- frontend/tests/legacy/
- frontend/tests/playwright/
- specs/changes/fix-prod-history-multiselect-filter/

### ci-cd-gatekeeper
- contracts/
- specs/changes/fix-prod-history-multiselect-filter/

### implementation-planner
- frontend/src/production-history/
- frontend/src/shared-ui/
- frontend/src/shared-composables/
- frontend/src/core/
- specs/changes/fix-prod-history-multiselect-filter/

### frontend-engineer
- frontend/src/production-history/
- frontend/src/shared-ui/
- frontend/src/shared-composables/
- frontend/src/core/
- frontend/tests/validation/
- frontend/tests/legacy/
- frontend/tests/playwright/
- specs/changes/fix-prod-history-multiselect-filter/

### ui-ux-reviewer
- frontend/src/production-history/
- frontend/src/shared-ui/
- contracts/css/
- specs/changes/fix-prod-history-multiselect-filter/

### visual-reviewer
- frontend/src/production-history/
- frontend/src/shared-ui/
- specs/changes/fix-prod-history-multiselect-filter/

### qa-reviewer
- specs/changes/fix-prod-history-multiselect-filter/
- frontend/tests/

## Context Expansion Requests

<!--
Agents must request context expansion instead of reading outside their work
packet. Format example for real requests:

- request-id: CER-001
  requested_paths:
    - src/example.ts
  reason: why this file is required
  status: pending
-->
-

## Approved Expansions
-
