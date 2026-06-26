# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- reject-history backend query/prefilter layer (route + service + cache + worker)
- reject-history frontend filter UI + DuckDB composable + page CSS
- API request contract (reject-history query endpoints)
- data-shape contract (reject_dataset query_id_input / cache key)

## Allowed Paths
- specs/changes/rh-remove-supplementary-filter/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/routes/reject_history_routes.py
- src/mes_dashboard/services/reject_history_service.py
- src/mes_dashboard/services/reject_dataset_cache.py
- src/mes_dashboard/services/reject_query_job_service.py
- src/mes_dashboard/services/reason_filter_cache.py
- src/mes_dashboard/workers/reject_history_worker.py
- src/mes_dashboard/sql/reject_history/
- frontend/src/reject-history/
- frontend/src/core/reject-history-filters.ts
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/openapi.json
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- tests/test_reject_history_service.py
- tests/test_reject_history_routes.py
- tests/test_reject_history_async_routes.py
- tests/test_reject_dataset_cache.py
- tests/test_reject_query_job_service.py
- tests/test_reject_history_unified_job.py
- tests/integration/test_reject_history_rq_async.py
- tests/e2e/test_reject_history_e2e.py
- tests/contract/samples/
- frontend/tests/playwright/reject-history-filter.spec.ts
- frontend/tests/validation/useRejectHistory.validation.test.js

## Required Contracts
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md

## Required Tests
- tests/test_reject_history_service.py
- tests/test_reject_history_routes.py
- tests/test_reject_history_async_routes.py
- tests/test_reject_dataset_cache.py
- tests/test_reject_query_job_service.py
- tests/test_reject_history_unified_job.py
- tests/integration/test_reject_history_rq_async.py
- tests/e2e/test_reject_history_e2e.py
- frontend/tests/playwright/reject-history-filter.spec.ts
- frontend/tests/validation/useRejectHistory.validation.test.js

## Agent Work Packets

### change-classifier
- specs/changes/rh-remove-supplementary-filter/
- specs/context/project-map.md
- specs/context/contracts-index.md

### contract-reviewer
- specs/changes/rh-remove-supplementary-filter/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/openapi.json
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md

### test-strategist
- specs/changes/rh-remove-supplementary-filter/
- tests/test_reject_history_service.py
- tests/test_reject_history_routes.py
- tests/test_reject_history_async_routes.py
- tests/test_reject_dataset_cache.py
- tests/test_reject_query_job_service.py
- tests/test_reject_history_unified_job.py
- tests/integration/test_reject_history_rq_async.py
- tests/e2e/test_reject_history_e2e.py
- frontend/tests/playwright/reject-history-filter.spec.ts
- frontend/tests/validation/useRejectHistory.validation.test.js

### ci-cd-gatekeeper
- specs/changes/rh-remove-supplementary-filter/

### implementation-planner
- specs/changes/rh-remove-supplementary-filter/
- specs/context/project-map.md
- specs/context/contracts-index.md

### backend-engineer
- specs/changes/rh-remove-supplementary-filter/
- src/mes_dashboard/routes/reject_history_routes.py
- src/mes_dashboard/services/reject_history_service.py
- src/mes_dashboard/services/reject_dataset_cache.py
- src/mes_dashboard/services/reject_query_job_service.py
- src/mes_dashboard/services/reason_filter_cache.py
- src/mes_dashboard/workers/reject_history_worker.py
- src/mes_dashboard/sql/reject_history/
- tests/test_reject_history_service.py
- tests/test_reject_history_routes.py
- tests/test_reject_history_async_routes.py
- tests/test_reject_dataset_cache.py
- tests/test_reject_query_job_service.py
- tests/test_reject_history_unified_job.py
- tests/integration/test_reject_history_rq_async.py
- tests/contract/samples/

### frontend-engineer
- specs/changes/rh-remove-supplementary-filter/
- frontend/src/reject-history/
- frontend/src/core/reject-history-filters.ts
- frontend/tests/playwright/reject-history-filter.spec.ts
- frontend/tests/validation/useRejectHistory.validation.test.js

### ui-ux-reviewer
- specs/changes/rh-remove-supplementary-filter/
- frontend/src/reject-history/

### visual-reviewer
- specs/changes/rh-remove-supplementary-filter/
- frontend/src/reject-history/

### qa-reviewer
- specs/changes/rh-remove-supplementary-filter/

## Context Expansion Requests

- request-id: CER-001
  requested_paths:
    - src/mes_dashboard/services/reject_dataset_cache.py
    - src/mes_dashboard/services/reject_history_service.py
    - src/mes_dashboard/services/reject_query_job_service.py
    - src/mes_dashboard/services/reason_filter_cache.py
  reason: Services directory truncated in project-map.md (cap=50); reject-history service/cache filenames unconfirmable from index alone. Required for backend-engineer to edit _build_base_where, _build_where_clause, execute_primary_query, and query_id_input.
  status: approved

## Approved Expansions
- CER-001: src/mes_dashboard/services/reject_history_service.py, reject_dataset_cache.py, reject_query_job_service.py, reason_filter_cache.py — approved; these are confirmed in-scope edit sites from prior conversation investigation.
