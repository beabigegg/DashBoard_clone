# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- yield-alert-center backend request handling & query hashing (routes)
- yield-alert-center dataset cache / Oracle detail SQL (process_type LIKE patterns, query_id hash)
- yield-alert-center filter-options / cross-filter-options SQL runtime (workcenter_groups source swap)
- yield-alert-center frontend page (process-type selector, force-requery, validation)
- API / data-shape / business-rules contracts for the yield-alert endpoints

## Allowed Paths
- specs/changes/yield-alert-filter-expansion/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/routes/yield_alert_routes.py
- src/mes_dashboard/services/yield_alert_dataset_cache.py
- src/mes_dashboard/services/yield_alert_sql_runtime.py
- src/mes_dashboard/services/filter_cache.py
- src/mes_dashboard/config/workcenter_groups.py
- src/mes_dashboard/sql/yield_alert/
- src/mes_dashboard/core/request_validation.py
- frontend/src/yield-alert-center/
- frontend/tests/validation/useYieldAlert.validation.test.js
- frontend/tests/yield-alert/
- frontend/tests/abort/yield-alert-abort.test.js
- frontend/tests/legacy/yield-alert-center-shell-contract.test.js
- frontend/tests/legacy/yield-alert-center-utils.test.js
- frontend/tests/playwright/yield-alert-center.spec.ts
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/openapi.json
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/css/css-contract.md
- tests/e2e/test_yield_alert_e2e.py
- tests/contract/samples/
- tests/contract/response-samples.json
- tests/contract/test_capture_samples.py
- tests/property/test_cross_filter.py
- tests/
- .github/workflows
- docs/architecture/ci-workflow.md

(`filter_cache.py` and `config/workcenter_groups.py` are read-only to confirm the shared path is NOT modified — the change re-points the page away from them.)

## Required Contracts
- contracts/api/api-contract.md
- contracts/api/openapi.json
- contracts/openapi.json
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md

## Required Tests
- frontend/tests/validation/useYieldAlert.validation.test.js
- frontend/tests/yield-alert/App.cross-filter.test.js
- frontend/tests/playwright/yield-alert-center.spec.ts
- tests/e2e/test_yield_alert_e2e.py
- tests/property/test_cross_filter.py
- tests/contract/ (sample capture for yield-alert endpoints)
- backend unit test for yield-alert request validation / query_id hash (exact file to be located by implementation-planner under tests/)

## Agent Work Packets
<!-- One sub-section per required agent. Each path list must be a subset of Allowed Paths above.
     Add or remove sub-sections to match Required Agents in change-classification.md.
     These sub-sections are documentation only — gate enforces Allowed Paths, not individual packets. -->

### change-classifier
- specs/changes/yield-alert-filter-expansion/
- specs/context/project-map.md
- specs/context/contracts-index.md

### implementation-planner
- specs/changes/yield-alert-filter-expansion/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/routes/yield_alert_routes.py
- src/mes_dashboard/services/yield_alert_dataset_cache.py
- src/mes_dashboard/services/yield_alert_sql_runtime.py
- src/mes_dashboard/services/filter_cache.py
- src/mes_dashboard/config/workcenter_groups.py
- src/mes_dashboard/sql/yield_alert/
- frontend/src/yield-alert-center/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md

### backend-engineer
- specs/changes/yield-alert-filter-expansion/
- src/mes_dashboard/routes/yield_alert_routes.py
- src/mes_dashboard/services/yield_alert_dataset_cache.py
- src/mes_dashboard/services/yield_alert_sql_runtime.py
- src/mes_dashboard/services/filter_cache.py
- src/mes_dashboard/config/workcenter_groups.py
- src/mes_dashboard/sql/yield_alert/
- src/mes_dashboard/core/request_validation.py
- tests/e2e/test_yield_alert_e2e.py
- tests/property/test_cross_filter.py
- tests/contract/samples/
- tests/contract/response-samples.json
- tests/contract/test_capture_samples.py
- tests/

### frontend-engineer
- specs/changes/yield-alert-filter-expansion/
- frontend/src/yield-alert-center/
- frontend/tests/validation/useYieldAlert.validation.test.js
- frontend/tests/yield-alert/
- frontend/tests/abort/yield-alert-abort.test.js
- frontend/tests/legacy/yield-alert-center-shell-contract.test.js
- frontend/tests/legacy/yield-alert-center-utils.test.js
- frontend/tests/playwright/yield-alert-center.spec.ts

### test-strategist
- specs/changes/yield-alert-filter-expansion/
- frontend/tests/validation/useYieldAlert.validation.test.js
- frontend/tests/yield-alert/
- frontend/tests/playwright/yield-alert-center.spec.ts
- tests/e2e/test_yield_alert_e2e.py
- tests/property/test_cross_filter.py
- tests/contract/samples/
- tests/contract/test_capture_samples.py

### contract-reviewer
- specs/changes/yield-alert-filter-expansion/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/openapi.json
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md

### ui-ux-reviewer
- specs/changes/yield-alert-filter-expansion/
- frontend/src/yield-alert-center/
- contracts/css/css-contract.md

### qa-reviewer
- specs/changes/yield-alert-filter-expansion/
- src/mes_dashboard/routes/yield_alert_routes.py
- src/mes_dashboard/services/yield_alert_dataset_cache.py
- src/mes_dashboard/services/yield_alert_sql_runtime.py
- frontend/src/yield-alert-center/

### ci-cd-gatekeeper
- specs/changes/yield-alert-filter-expansion/
- .github/workflows
- docs/architecture/ci-workflow.md

## Context Expansion Requests
-

## Approved Expansions
- CER-001: src/mes_dashboard/services/yield_alert_dataset_cache.py, src/mes_dashboard/services/yield_alert_sql_runtime.py, src/mes_dashboard/routes/yield_alert_routes.py — folded into Allowed Paths above.
- CER-002: tests/ — folded into Allowed Paths above (backend unit-test file location for yield-alert request validation / query_id hashing to be confirmed by implementation-planner).
- CER-003: .github/workflows, docs/architecture/ci-workflow.md — folded into Allowed Paths above (ci-cd-gatekeeper reference for existing gate structure).
