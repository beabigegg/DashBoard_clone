# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- Production History Workcenter × Equipment Matrix aggregation (backend service layer)
- Data-shape contract: matrix `COUNT(DISTINCT CONTAINERNAME)` semantics
- Business rule PH-02: lot-count semantics

## Allowed Paths
- specs/changes/fix-matrix-distinct-count/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/services/production_history_sql_runtime.py
- src/mes_dashboard/sql/production_history/
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/ci/
- tests/test_production_history_sql_runtime.py
- tests/test_api_contract.py

## Required Contracts
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md

## Required Tests
- tests/test_production_history_sql_runtime.py
- tests/test_api_contract.py

## Agent Work Packets

### change-classifier
- specs/changes/fix-matrix-distinct-count/
- specs/context/project-map.md
- specs/context/contracts-index.md

### spec-architect
- specs/changes/fix-matrix-distinct-count/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/services/production_history_sql_runtime.py
- src/mes_dashboard/sql/production_history/
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md

### test-strategist
- specs/changes/fix-matrix-distinct-count/
- src/mes_dashboard/services/production_history_sql_runtime.py
- tests/test_production_history_sql_runtime.py
- tests/test_api_contract.py
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md

### backend-engineer
- specs/changes/fix-matrix-distinct-count/
- src/mes_dashboard/services/production_history_sql_runtime.py
- src/mes_dashboard/sql/production_history/
- tests/test_production_history_sql_runtime.py
- tests/test_api_contract.py
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md

### contract-reviewer
- specs/changes/fix-matrix-distinct-count/
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md

### ci-cd-gatekeeper
- specs/changes/fix-matrix-distinct-count/
- contracts/ci/

### qa-reviewer
- specs/changes/fix-matrix-distinct-count/
- src/mes_dashboard/services/production_history_sql_runtime.py
- tests/test_production_history_sql_runtime.py
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md

## Context Expansion Requests
- request-id: CER-001
  requested_paths:
    - tests/test_production_history_sql_runtime.py
  reason: project-map tests/ listing truncated at cap=50; exact test filename for the matrix functions unconfirmed.
  status: resolved
  resolution: main Claude confirmed the file exists; added to Allowed Paths.
- request-id: CER-002
  requested_paths:
    - frontend/src/production-history/components/ProductionMatrix.vue
  reason: read-only verification that the consumer reads count/month_counts per node and no frontend change is implied.
  status: resolved
  resolution: main Claude confirmed the file exists and consumes count/month_counts; node shape unchanged so no frontend edit and no read needed — regression-report asserts non-impact from contract/test evidence.

## Approved Expansions
-
