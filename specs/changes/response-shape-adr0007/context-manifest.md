# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- API response-shape contract (all 158 endpoints)
- Contract-test harness (`tests/contract/`)
- Data-shape conformance gate
- CI contract gate

## Allowed Paths
- specs/changes/response-shape-adr0007/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/api/
- contracts/data/
- contracts/ci/
- contracts/openapi.json
- contracts/CHANGELOG.md
- docs/adr/
- tests/contract/
- tests/test_api_contract.py
- src/mes_dashboard/routes/
- src/mes_dashboard/core/response.py
- src/mes_dashboard/services/auth_service.py
- src/mes_dashboard/app.py
- .github/workflows/contract-driven-gates.yml

## Required Contracts
- contracts/api/api-contract.md
- contracts/api/error-format.md
- contracts/data/data-shape-contract.md
- contracts/ci/ci-gate-contract.md
- contracts/openapi.json

## Required Tests
- tests/contract/capture_samples.py (new)
- tests/contract/response-samples.json (new)
- tests/contract/samples/*.json (new)

## Agent Work Packets

### contract-reviewer
- specs/changes/response-shape-adr0007/
- contracts/api/
- contracts/data/
- contracts/openapi.json
- tests/contract/

### test-strategist
- specs/changes/response-shape-adr0007/
- tests/contract/
- tests/test_api_contract.py
- contracts/api/api-contract.md
- contracts/data/

### ci-cd-gatekeeper
- specs/changes/response-shape-adr0007/
- contracts/ci/
- .github/workflows/contract-driven-gates.yml
- tests/contract/

### implementation-planner
- specs/changes/response-shape-adr0007/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/data/
- docs/adr/

### backend-engineer
- specs/changes/response-shape-adr0007/
- contracts/api/
- contracts/data/
- contracts/openapi.json
- contracts/CHANGELOG.md
- tests/contract/
- src/mes_dashboard/routes/
- src/mes_dashboard/core/response.py
- src/mes_dashboard/services/auth_service.py
- src/mes_dashboard/app.py

### qa-reviewer
- specs/changes/response-shape-adr0007/
- contracts/api/api-contract.md
- contracts/openapi.json
- tests/contract/

## Context Expansion Requests
-

## Approved Expansions
- CER-001: contracts/openapi.json, tests/contract/README.md, tests/contract/response-samples.example.json, tests/test_api_contract.py, .github/workflows/contract-driven-gates.yml — approved (all exist in Allowed Paths)
- CER-002: src/mes_dashboard/routes/, src/mes_dashboard/core/response.py, src/mes_dashboard/services/auth_service.py — approved read-only for route signatures, wrapper shape, and auth flow
