# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- frontend query-tool feature module — sub-tab switching / client-side query caching

## Allowed Paths
- specs/changes/query-tool-subtab-cache/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/query-tool/composables/
- frontend/src/query-tool/App.vue
- frontend/tests/query-tool/
- frontend/tests/legacy/query-tool-composables.test.js

## Required Contracts
- none

## Required Tests
- frontend/tests/query-tool/ (existing useLotEquipmentQuery.test.js, useLotDetail.pagination.test.js, plus new cache-behavior specs)
- frontend/tests/legacy/query-tool-composables.test.js (existing; may need updates if it asserts current always-requery behavior)

## Agent Work Packets

### change-classifier
- specs/changes/query-tool-subtab-cache/
- specs/context/project-map.md
- specs/context/contracts-index.md

### implementation-planner
- specs/changes/query-tool-subtab-cache/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/query-tool/composables/
- frontend/src/query-tool/App.vue

### frontend-engineer
- specs/changes/query-tool-subtab-cache/
- frontend/src/query-tool/composables/
- frontend/src/query-tool/App.vue
- frontend/tests/query-tool/
- frontend/tests/legacy/query-tool-composables.test.js

### test-strategist
- specs/changes/query-tool-subtab-cache/
- frontend/src/query-tool/composables/
- frontend/tests/query-tool/
- frontend/tests/legacy/query-tool-composables.test.js

### qa-reviewer
- specs/changes/query-tool-subtab-cache/
- frontend/src/query-tool/composables/
- frontend/tests/query-tool/

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
- none at classification time — indexes were sufficient to propose all candidate paths. App.vue is included read-only for call-site verification; if the sub-tab call sites live in a component under frontend/src/query-tool/components/ rather than App.vue, raise a CER to add that specific file rather than widening to the whole components/ tree.

## Approved Expansions
-
