# Context Manifest — ai-pipeline-upgrade

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- AI query pipeline (services layer)
- AI function registry config (`ai_functions.yaml`)
- AI query session store (`_SESSION_STORE`)

## Allowed Paths
- specs/changes/ai-pipeline-upgrade/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/services/ai_function_registry.py
- src/mes_dashboard/services/ai_functions.yaml
- src/mes_dashboard/services/ai_query_service.py
- src/mes_dashboard/services/ai_query_understanding.py
- src/mes_dashboard/services/production_history_service.py
- src/mes_dashboard/services/resource_history_service.py
- src/mes_dashboard/services/qc_gate_service.py
- src/mes_dashboard/routes/ai_routes.py
- tests/test_ai_query_service.py
- tests/test_ai_function_registry.py
- tests/test_ai_query_understanding.py
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/business/business-rules.md
- contracts/data/data-shape-contract.md

## Required Contracts
- contracts/api/api-contract.md
- contracts/business/business-rules.md
- contracts/data/data-shape-contract.md

## Required Tests
- tests/test_ai_query_service.py
- tests/test_ai_function_registry.py
- tests/test_ai_query_understanding.py

## Agent Work Packets

### spec-architect
- specs/changes/ai-pipeline-upgrade/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/services/ai_function_registry.py
- src/mes_dashboard/services/ai_query_service.py
- src/mes_dashboard/services/ai_query_understanding.py
- src/mes_dashboard/services/ai_functions.yaml
- contracts/api/api-contract.md
- contracts/business/business-rules.md
- contracts/data/data-shape-contract.md

### contract-reviewer
- specs/changes/ai-pipeline-upgrade/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/business/business-rules.md
- contracts/data/data-shape-contract.md

### test-strategist
- specs/changes/ai-pipeline-upgrade/
- tests/test_ai_query_service.py
- tests/test_ai_function_registry.py
- tests/test_ai_query_understanding.py

### implementation-planner
- specs/changes/ai-pipeline-upgrade/
- src/mes_dashboard/services/ai_function_registry.py
- src/mes_dashboard/services/ai_query_service.py
- src/mes_dashboard/services/ai_query_understanding.py
- src/mes_dashboard/services/ai_functions.yaml

### backend-engineer
- specs/changes/ai-pipeline-upgrade/
- src/mes_dashboard/services/ai_function_registry.py
- src/mes_dashboard/services/ai_functions.yaml
- src/mes_dashboard/services/ai_query_service.py
- src/mes_dashboard/services/ai_query_understanding.py
- src/mes_dashboard/services/production_history_service.py
- src/mes_dashboard/services/resource_history_service.py
- src/mes_dashboard/services/qc_gate_service.py
- src/mes_dashboard/routes/ai_routes.py
- tests/test_ai_query_service.py
- tests/test_ai_function_registry.py
- tests/test_ai_query_understanding.py

### qa-reviewer
- specs/changes/ai-pipeline-upgrade/
- contracts/

## Context Expansion Requests
- request-id: CER-001
  requested_paths:
    - src/mes_dashboard/services/production_history_service.py
    - src/mes_dashboard/services/resource_history_service.py
    - src/mes_dashboard/services/qc_gate_service.py
  reason: Change registers three new AI functions pointing at these callables; spec-architect and backend-engineer need their signatures and param schemas to author correct ai_functions.yaml entries and data-shape contract rules.
  status: approved

## Approved Expansions
- CER-001 approved: production_history_service, resource_history_service, qc_gate_service signatures needed for param schema authoring.
