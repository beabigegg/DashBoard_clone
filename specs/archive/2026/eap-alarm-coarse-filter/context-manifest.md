# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- eap-alarm coarse-filter (backend service + async worker + route)
- eap-alarm frontend filter bar + filter composable
- shared container filter cache (product-dim options source)
- query spool store (eap_alarm namespace, schema_version 3)

## Allowed Paths
- specs/changes/eap-alarm-coarse-filter/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/openapi.json
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/CHANGELOG.md
- src/mes_dashboard/services/eap_alarm_cache.py
- src/mes_dashboard/services/eap_alarm_service.py
- src/mes_dashboard/services/container_filter_cache.py
- src/mes_dashboard/workers/eap_alarm_worker.py
- src/mes_dashboard/routes/eap_alarm_routes.py
- frontend/src/eap-alarm/
- tests/test_eap_alarm_service.py
- tests/integration/test_eap_alarm_rq_async.py
- tests/integration/test_eap_alarm_coarse_filter.py
- tests/integration/test_eap_alarm_data_boundary.py
- tests/integration/test_eap_alarm_resilience.py
- tests/e2e/test_eap_alarm_e2e.py
- frontend/tests/playwright/eap-alarm-filters.spec.ts
- frontend/tests/unit/eap-alarm-filter.test.js
- docs/adr/0008-eap-alarm-coarse-spool-detail-join.md

## Required Contracts
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md

## Required Tests
- tests/test_eap_alarm_service.py
- tests/integration/test_eap_alarm_coarse_filter.py
- tests/integration/test_eap_alarm_rq_async.py
- tests/integration/test_eap_alarm_data_boundary.py
- tests/integration/test_eap_alarm_resilience.py
- frontend/tests/playwright/eap-alarm-filters.spec.ts
- frontend/tests/unit/eap-alarm-filter.test.js

## Agent Work Packets

### spec-architect
- specs/changes/eap-alarm-coarse-filter/
- specs/context/project-map.md
- specs/context/contracts-index.md
- docs/adr/0008-eap-alarm-coarse-spool-detail-join.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md

### contract-reviewer
- specs/changes/eap-alarm-coarse-filter/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/CHANGELOG.md

### test-strategist
- specs/changes/eap-alarm-coarse-filter/
- tests/test_eap_alarm_service.py
- tests/integration/test_eap_alarm_data_boundary.py
- tests/integration/test_eap_alarm_resilience.py
- frontend/tests/unit/eap-alarm-filter.test.js

### implementation-planner
- specs/changes/eap-alarm-coarse-filter/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md

### backend-engineer
- specs/changes/eap-alarm-coarse-filter/
- src/mes_dashboard/services/eap_alarm_cache.py
- src/mes_dashboard/services/eap_alarm_service.py
- src/mes_dashboard/services/container_filter_cache.py
- src/mes_dashboard/workers/eap_alarm_worker.py
- src/mes_dashboard/routes/eap_alarm_routes.py
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/openapi.json
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/CHANGELOG.md
- tests/test_eap_alarm_service.py
- tests/integration/test_eap_alarm_rq_async.py
- tests/integration/test_eap_alarm_coarse_filter.py
- tests/integration/test_eap_alarm_data_boundary.py
- tests/integration/test_eap_alarm_resilience.py

### frontend-engineer
- specs/changes/eap-alarm-coarse-filter/
- frontend/src/eap-alarm/
- frontend/tests/unit/eap-alarm-filter.test.js
- frontend/tests/playwright/eap-alarm-filters.spec.ts

### ui-ux-reviewer
- specs/changes/eap-alarm-coarse-filter/
- frontend/src/eap-alarm/

### qa-reviewer
- specs/changes/eap-alarm-coarse-filter/

## Context Expansion Requests
- request-id: CER-001
  requested_paths:
    - tests/test_eap_alarm_service.py
    - src/mes_dashboard/services/container_filter_cache.py
    - docs/adr/0008-eap-alarm-coarse-spool-detail-join.md
  reason: Confirm these exist before agents read them
  status: resolved — all three paths confirmed present
