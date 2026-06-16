# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- yield-alert-center (backend service + spool builder + SQL + route)
- yield-alert-center frontend app (Vue + DuckDB compute layer)
- shared spool infrastructure (core/spool_routes.py, spool warmup / RQ worker) — read-mostly
- shared frontend filter orchestrator (useFilterOrchestrator.ts) — additive-only

## Allowed Paths
- specs/changes/yield-alert-spool-refactor/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/css/css-contract.md
- contracts/ci/ci-gate-contract.md
- src/mes_dashboard/services/yield_alert_dataset_cache.py
- src/mes_dashboard/services/yield_alert_service.py
- src/mes_dashboard/routes/yield_alert_routes.py
- src/mes_dashboard/routes/spool_routes.py
- src/mes_dashboard/core/spool_routes.py
- src/mes_dashboard/core/spool_pipeline.py
- src/mes_dashboard/core/query_spool_store.py
- src/mes_dashboard/sql/yield_alert/
- frontend/src/yield-alert-center/
- frontend/src/shared-composables/useFilterOrchestrator.ts
- frontend/src/core/duckdb-client.ts
- tests/test_yield_alert_dataset_cache.py
- tests/test_yield_alert_service.py
- tests/test_yield_alert_routes.py
- tests/e2e/test_yield_alert_e2e.py
- tests/stress/test_yield_alert_stress.py
- frontend/tests/validation/useYieldAlert.validation.test.js
- frontend/tests/yield-alert/App.cross-filter.test.js
- frontend/tests/abort/yield-alert-abort.test.js
- frontend/tests/legacy/yield-alert-center-shell-contract.test.js
- frontend/tests/legacy/yield-alert-center-utils.test.js
- tests/contract/response-samples.json
- docs/architecture/cache-spool-patterns.md

## Required Contracts
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json (regen after endpoint/schema edits)
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/css/css-contract.md (confirm-only, likely no edit)
- contracts/ci/ci-gate-contract.md (confirm-only, likely no edit)

## Required Tests
- tests/test_yield_alert_dataset_cache.py (and other backend tests/test_yield_alert_*.py)
- tests/e2e/test_yield_alert_e2e.py
- tests/stress/test_yield_alert_stress.py
- frontend/tests/validation/useYieldAlert.validation.test.js
- frontend/tests/yield-alert/App.cross-filter.test.js
- frontend/tests/abort/yield-alert-abort.test.js
- frontend/tests/legacy/yield-alert-center-shell-contract.test.js
- frontend/tests/legacy/yield-alert-center-utils.test.js

## Agent Work Packets

### change-classifier
- specs/changes/yield-alert-spool-refactor/
- specs/context/project-map.md
- specs/context/contracts-index.md

### spec-architect
- specs/changes/yield-alert-spool-refactor/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/api/api-contract.md
- src/mes_dashboard/services/yield_alert_dataset_cache.py
- src/mes_dashboard/services/yield_alert_service.py
- src/mes_dashboard/core/spool_routes.py
- src/mes_dashboard/core/spool_pipeline.py
- src/mes_dashboard/sql/yield_alert/
- docs/architecture/cache-spool-patterns.md

### contract-reviewer
- specs/changes/yield-alert-spool-refactor/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/css/css-contract.md
- contracts/ci/ci-gate-contract.md
- tests/contract/response-samples.json

### test-strategist
- specs/changes/yield-alert-spool-refactor/
- tests/test_yield_alert_dataset_cache.py
- tests/test_yield_alert_service.py
- tests/test_yield_alert_routes.py
- tests/e2e/test_yield_alert_e2e.py
- tests/stress/test_yield_alert_stress.py
- frontend/tests/validation/useYieldAlert.validation.test.js
- frontend/tests/yield-alert/App.cross-filter.test.js
- frontend/tests/abort/yield-alert-abort.test.js
- frontend/tests/legacy/yield-alert-center-utils.test.js

### ci-cd-gatekeeper
- specs/changes/yield-alert-spool-refactor/
- contracts/ci/ci-gate-contract.md

### implementation-planner
- specs/changes/yield-alert-spool-refactor/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md

### backend-engineer
- specs/changes/yield-alert-spool-refactor/
- src/mes_dashboard/services/yield_alert_dataset_cache.py
- src/mes_dashboard/services/yield_alert_service.py
- src/mes_dashboard/routes/yield_alert_routes.py
- src/mes_dashboard/routes/spool_routes.py
- src/mes_dashboard/core/spool_routes.py
- src/mes_dashboard/core/spool_pipeline.py
- src/mes_dashboard/core/query_spool_store.py
- src/mes_dashboard/sql/yield_alert/
- tests/test_yield_alert_dataset_cache.py
- tests/test_yield_alert_service.py
- tests/test_yield_alert_routes.py

### frontend-engineer
- specs/changes/yield-alert-spool-refactor/
- frontend/src/yield-alert-center/
- frontend/src/shared-composables/useFilterOrchestrator.ts
- frontend/src/core/duckdb-client.ts
- frontend/tests/validation/useYieldAlert.validation.test.js
- frontend/tests/yield-alert/App.cross-filter.test.js
- frontend/tests/abort/yield-alert-abort.test.js
- frontend/tests/legacy/yield-alert-center-utils.test.js

### stress-soak-engineer
- specs/changes/yield-alert-spool-refactor/
- tests/stress/test_yield_alert_stress.py
- src/mes_dashboard/services/yield_alert_dataset_cache.py
- src/mes_dashboard/core/spool_pipeline.py

### ui-ux-reviewer
- specs/changes/yield-alert-spool-refactor/
- frontend/src/yield-alert-center/
- contracts/css/css-contract.md

### visual-reviewer
- specs/changes/yield-alert-spool-refactor/
- frontend/src/yield-alert-center/

### qa-reviewer
- specs/changes/yield-alert-spool-refactor/
- contracts/business/business-rules.md
- contracts/data/data-shape-contract.md

## Context Expansion Requests

- request-id: CER-001
  requested_paths:
    - tests/test_yield_alert_*.py (exact filenames)
  reason: project-map truncates the tests/ listing at cap=50; the precise backend yield-alert test filenames are not enumerated. Confirm before backend test edits.
  status: pending

- request-id: CER-002
  requested_paths:
    - src/mes_dashboard/services/ (entries beyond cap=50 truncation)
  reason: services listing is truncated; a yield_alert_query_job_service or warmup module may exist and need editing for the spool-shape change.
  status: pending

## Approved Expansions
-
