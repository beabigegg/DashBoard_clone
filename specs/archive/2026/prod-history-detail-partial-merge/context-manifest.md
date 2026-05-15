# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- Backend production-history report module (service + sql_runtime + routes + job_service)
- Frontend production-history app + shared DataTable (additive only)
- Contracts: api / business / (data-shape if enumerated)
- Tests: unit (Python + Vitest), integration, e2e (informational)

## Allowed Paths
- specs/changes/prod-history-detail-partial-merge/
- specs/archive/2025/prod-history-detail-raw-rows/
- specs/context/
- contracts/api/
- contracts/business/
- contracts/data/
- contracts/ci/
- contracts/css/
- src/mes_dashboard/services/
- src/mes_dashboard/routes/
- src/mes_dashboard/sql/production_history/
- src/mes_dashboard/core/
- frontend/src/production-history/
- frontend/src/shared-ui/components/
- frontend/tests/
- tests/
- .github/workflows/

## Required Contracts
- contracts/api/api-contract.md (update — add `partial_count` field to detail row schema)
- contracts/business/business-rules.md (update — document 5-key aggregation rule + strict guard fallback)
- contracts/data/data-shape-contract.md (read; update only if it enumerates detail row fields)

## Required Tests
- Unit: aggregation key correctness, MAX(trackout_time)/SUM(trackout_qty) math, strict-guard fallback, partial_count counting
- Integration: DuckDB SQL ↔ pandas fallback parity; CSV export ↔ API parity
- e2e (informational): existing production-history specs run as regression

## Agent Work Packets

### change-classifier
- specs/changes/prod-history-detail-partial-merge/
- specs/context/project-map.md
- specs/context/contracts-index.md

### contract-reviewer
- specs/changes/prod-history-detail-partial-merge/
- specs/archive/2025/prod-history-detail-raw-rows/
- contracts/api/
- contracts/business/
- contracts/data/

### test-strategist
- specs/changes/prod-history-detail-partial-merge/
- contracts/api/
- contracts/business/
- tests/
- frontend/tests/

### ci-cd-gatekeeper
- specs/changes/prod-history-detail-partial-merge/
- contracts/ci/
- .github/workflows/

### implementation-planner
- specs/changes/prod-history-detail-partial-merge/
- contracts/api/
- contracts/business/
- src/mes_dashboard/services/
- src/mes_dashboard/routes/
- src/mes_dashboard/sql/production_history/
- frontend/src/production-history/
- frontend/src/shared-ui/components/

### backend-engineer
- specs/changes/prod-history-detail-partial-merge/
- contracts/api/
- contracts/business/
- contracts/data/
- src/mes_dashboard/services/
- src/mes_dashboard/routes/
- src/mes_dashboard/sql/production_history/
- src/mes_dashboard/core/
- tests/

### frontend-engineer
- specs/changes/prod-history-detail-partial-merge/
- contracts/api/
- contracts/css/
- frontend/src/production-history/
- frontend/src/shared-ui/components/
- frontend/tests/

### ui-ux-reviewer
- specs/changes/prod-history-detail-partial-merge/
- contracts/css/
- frontend/src/production-history/
- frontend/src/shared-ui/components/

### visual-reviewer
- specs/changes/prod-history-detail-partial-merge/
- frontend/src/production-history/
- frontend/tests/

### qa-reviewer
- specs/changes/prod-history-detail-partial-merge/
- contracts/
- tests/
- frontend/tests/

## Context Expansion Requests

<!--
Agents must request context expansion instead of reading outside their work
packet. Format example:

- request-id: CER-001
  requested_paths:
    - src/example.ts
  reason: why this file is required
  status: pending
-->
-

## Approved Expansions
-
