# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- yield-alert-center (良率警報中心): backend SQL aggregation + route, frontend Vue/TS CSV export, business-rules contract.

## Allowed Paths
- specs/changes/yield-alert-kpi-csv-parity/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/business/business-rules.md
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/data/data-shape-contract.md
- contracts/CHANGELOG.md
- contracts/openapi.json
- src/mes_dashboard/services/yield_alert_sql_runtime.py
- src/mes_dashboard/routes/yield_alert_routes.py
- src/mes_dashboard/sql/yield_alert/
- frontend/src/yield-alert-center/
- tests/test_yield_alert_sql_runtime.py
- tests/test_yield_alert_service.py
- tests/test_yield_alert_routes.py
- tests/test_yield_alert_contracts.py
- tests/e2e/test_yield_alert_e2e.py
- tests/stress/test_yield_alert_stress.py
- tests/contract/samples/get_yield_alert_view.json
- tests/contract/samples/get_yield_alert_summary.json
- tests/contract/samples/get_yield_alert_alerts.json
- frontend/tests/unit/
- frontend/tests/playwright/

## Required Contracts
- contracts/business/business-rules.md (new YA-13 rule: KPI scope = alert-candidate scope + tx-dedup dimension)
- contracts/data/data-shape-contract.md (CSV numeric formatting)
- contracts/api/api-contract.md (summary field semantic note)
- contracts/CHANGELOG.md (version entry)

## Required Tests
- tests/test_yield_alert_sql_runtime.py (backend unit — _query_summary scope + tx-dedup)
- tests/test_yield_alert_service.py, tests/test_yield_alert_routes.py (integration — KPI↔CSV reconciliation)
- tests/test_yield_alert_contracts.py, tests/contract/samples/get_yield_alert_view.json, get_yield_alert_summary.json, get_yield_alert_alerts.json (contract pin)
- frontend/tests/unit/ (CSV rounding, toPcs formatting)
- frontend/tests/playwright/ (optional E2E, deferred to test-strategist)

## Agent Work Packets

### change-classifier
- specs/changes/yield-alert-kpi-csv-parity/
- specs/context/project-map.md
- specs/context/contracts-index.md

### spec-architect
- specs/changes/yield-alert-kpi-csv-parity/
- contracts/business/business-rules.md
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- src/mes_dashboard/services/yield_alert_sql_runtime.py
- src/mes_dashboard/routes/yield_alert_routes.py
- src/mes_dashboard/sql/yield_alert/
- frontend/src/yield-alert-center/

### implementation-planner
- specs/changes/yield-alert-kpi-csv-parity/
- contracts/business/business-rules.md
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- src/mes_dashboard/services/yield_alert_sql_runtime.py
- src/mes_dashboard/routes/yield_alert_routes.py
- src/mes_dashboard/sql/yield_alert/
- frontend/src/yield-alert-center/
- tests/test_yield_alert_sql_runtime.py
- tests/test_yield_alert_service.py
- tests/test_yield_alert_routes.py
- tests/test_yield_alert_contracts.py
- frontend/tests/unit/
- frontend/tests/playwright/

### bug-fix-engineer
- specs/changes/yield-alert-kpi-csv-parity/
- src/mes_dashboard/services/yield_alert_sql_runtime.py
- src/mes_dashboard/routes/yield_alert_routes.py
- frontend/src/yield-alert-center/
- tests/test_yield_alert_sql_runtime.py
- tests/test_yield_alert_service.py
- frontend/tests/unit/

### backend-engineer
- specs/changes/yield-alert-kpi-csv-parity/
- src/mes_dashboard/services/yield_alert_sql_runtime.py
- src/mes_dashboard/routes/yield_alert_routes.py
- src/mes_dashboard/sql/yield_alert/
- contracts/business/business-rules.md
- contracts/api/api-contract.md
- contracts/api/openapi.json
- contracts/openapi.json
- contracts/data/data-shape-contract.md
- contracts/CHANGELOG.md
- tests/test_yield_alert_sql_runtime.py
- tests/test_yield_alert_service.py
- tests/test_yield_alert_routes.py
- tests/test_yield_alert_contracts.py
- tests/contract/samples/get_yield_alert_view.json
- tests/contract/samples/get_yield_alert_summary.json
- tests/contract/samples/get_yield_alert_alerts.json

### frontend-engineer
- specs/changes/yield-alert-kpi-csv-parity/
- frontend/src/yield-alert-center/
- frontend/tests/unit/
- frontend/tests/playwright/

### test-strategist
- specs/changes/yield-alert-kpi-csv-parity/
- src/mes_dashboard/services/yield_alert_sql_runtime.py
- src/mes_dashboard/routes/yield_alert_routes.py
- frontend/src/yield-alert-center/
- tests/test_yield_alert_sql_runtime.py
- tests/test_yield_alert_service.py
- tests/test_yield_alert_routes.py
- tests/test_yield_alert_contracts.py
- tests/e2e/test_yield_alert_e2e.py
- frontend/tests/unit/
- frontend/tests/playwright/

### contract-reviewer
- specs/changes/yield-alert-kpi-csv-parity/
- contracts/business/business-rules.md
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/data/data-shape-contract.md
- contracts/CHANGELOG.md

### qa-reviewer
- specs/changes/yield-alert-kpi-csv-parity/
- contracts/business/business-rules.md
- contracts/data/data-shape-contract.md

## Context Expansion Requests

- request-id: CER-001
  requested_paths:
    - src/mes_dashboard/sql/yield_alert/
  reason: project-map truncates this directory; exact .sql template files backing _query_summary/_query_alerts not enumerated in the index. Needed by spec-architect/backend-engineer to confirm the dedup dimension.
  status: approved (folded into Allowed Paths above)
- request-id: CER-002
  requested_paths:
    - tests/test_yield_alert_sql_runtime.py
    - tests/test_yield_alert_service.py
    - tests/test_yield_alert_routes.py
    - tests/test_yield_alert_contracts.py
  reason: exact yield-alert backend test filenames confirmed via directory listing; narrowed from directory-level tests/ per project convention (context-manifest Allowed Paths must use directory-level paths or specific files, not broad globs).
  status: approved (folded into Allowed Paths above)

## Approved Expansions
- src/mes_dashboard/sql/yield_alert/ (CER-001)
- tests/test_yield_alert_sql_runtime.py, tests/test_yield_alert_service.py, tests/test_yield_alert_routes.py, tests/test_yield_alert_contracts.py (CER-002)
