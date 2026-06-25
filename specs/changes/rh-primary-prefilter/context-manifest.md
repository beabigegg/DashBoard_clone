# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- reject-history backend (service + route + SQL)
- reject-history frontend (FilterPanel, App, filters core)
- shared cross-filter consumption (container_filter_cache, production-history
  filter-options API — read/consume only)

## Allowed Paths
- specs/changes/rh-primary-prefilter/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/services/reject_history_service.py
- src/mes_dashboard/routes/reject_history_routes.py
- src/mes_dashboard/sql/reject_history/
- src/mes_dashboard/services/container_filter_cache.py
- frontend/src/reject-history/
- frontend/src/core/reject-history-filters.ts
- frontend/src/shared-ui/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/openapi.json
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md
- tests/test_reject_history_service.py
- tests/test_reject_history_routes.py
- tests/test_reject_history_async_routes.py
- tests/test_reject_history_unified_job.py
- tests/contract/
- frontend/tests/playwright/reject-history-filter.spec.ts
- frontend/tests/validation/useRejectHistory.validation.test.js
- src/mes_dashboard/services/reject_dataset_cache.py
- src/mes_dashboard/services/reject_query_job_service.py
- src/mes_dashboard/workers/reject_history_worker.py
- tests/test_reject_dataset_cache.py
- tests/test_reject_query_job_service.py

## Required Contracts
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/openapi.json
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md

## Required Tests
- tests/test_reject_history_service.py
- tests/test_reject_history_routes.py
- tests/test_reject_history_async_routes.py
- tests/contract/
- frontend/tests/playwright/reject-history-filter.spec.ts
- frontend/tests/validation/useRejectHistory.validation.test.js

## Agent Work Packets

### change-classifier
- specs/changes/rh-primary-prefilter/
- specs/context/project-map.md
- specs/context/contracts-index.md

### contract-reviewer
- specs/changes/rh-primary-prefilter/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/openapi.json
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md

### test-strategist
- specs/changes/rh-primary-prefilter/
- tests/test_reject_history_service.py
- tests/test_reject_history_routes.py
- tests/test_reject_history_async_routes.py
- tests/contract/
- frontend/tests/playwright/reject-history-filter.spec.ts
- frontend/tests/validation/useRejectHistory.validation.test.js

### ci-cd-gatekeeper
- specs/changes/rh-primary-prefilter/
- contracts/ci/ci-gate-contract.md

### implementation-planner
- specs/changes/rh-primary-prefilter/
- specs/context/project-map.md
- specs/context/contracts-index.md

### backend-engineer
- specs/changes/rh-primary-prefilter/
- src/mes_dashboard/services/reject_history_service.py
- src/mes_dashboard/routes/reject_history_routes.py
- src/mes_dashboard/sql/reject_history/
- src/mes_dashboard/services/container_filter_cache.py
- src/mes_dashboard/services/reject_dataset_cache.py
- src/mes_dashboard/services/reject_query_job_service.py
- src/mes_dashboard/workers/reject_history_worker.py
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- tests/test_reject_history_service.py
- tests/test_reject_history_routes.py
- tests/test_reject_history_async_routes.py
- tests/test_reject_history_unified_job.py
- tests/test_reject_dataset_cache.py
- tests/test_reject_query_job_service.py
- tests/contract/

### frontend-engineer
- specs/changes/rh-primary-prefilter/
- frontend/src/reject-history/
- frontend/src/core/reject-history-filters.ts
- frontend/src/shared-ui/
- frontend/tests/playwright/reject-history-filter.spec.ts
- frontend/tests/validation/useRejectHistory.validation.test.js

### ui-ux-reviewer
- specs/changes/rh-primary-prefilter/
- frontend/src/reject-history/
- frontend/src/shared-ui/

### qa-reviewer
- specs/changes/rh-primary-prefilter/
- contracts/

## Context Expansion Requests
- id: CER-1
  status: approved
  path: src/mes_dashboard/services/reject_dataset_cache.py
  reason: >
    Parity-critical (RHPF-05). The route imports execute_primary_query and
    _make_query_id from this module, and _build_where_clause / _prepare_sql are
    actually invoked here (execute_primary_query lines 804-1233, _execute_and_spool
    481-796). The three new BASE_WHERE prefilters must be threaded through this
    module's call into the service AND into _make_query_id (154) / spool key.
    Cannot inject prefilters into BASE_WHERE or guarantee cache/spool-key parity
    without editing this file.
- id: CER-2
  status: approved
  path: src/mes_dashboard/services/reject_query_job_service.py
  reason: >
    Legacy async job path (REJECT_HISTORY_USE_UNIFIED_JOB=off, default).
    execute_reject_query_job (124-191) consumes job_params and must forward the
    three new prefilter fields to the service so the async result matches sync.
- id: CER-3
  status: approved
  path: src/mes_dashboard/workers/reject_history_worker.py
  reason: >
    Unified async job path (REJECT_HISTORY_USE_UNIFIED_JOB=on). The reject_unified
    job built here must receive and apply the three prefilter fields from job_params
    for sync/async parity (RHPF-05).
- id: CER-4
  status: approved
  path: tests/test_reject_dataset_cache.py
  reason: >
    Covers _make_query_id / execute_primary_query / spool-key behavior changed by
    CER-1; new prefilter cache-key and BASE_WHERE assertions land here.
- id: CER-5
  status: approved
  path: tests/test_reject_query_job_service.py
  reason: >
    Covers execute_reject_query_job param forwarding changed by CER-2.

## Approved Expansions
- CER-1: src/mes_dashboard/services/reject_dataset_cache.py (parity: spool cache key + execute_primary_query call chain)
- CER-2: src/mes_dashboard/services/reject_query_job_service.py (parity: legacy async job param forwarding)
- CER-3: src/mes_dashboard/workers/reject_history_worker.py (parity: unified async job param forwarding)
- CER-4: tests/test_reject_dataset_cache.py (tests for CER-1 changes)
- CER-5: tests/test_reject_query_job_service.py (tests for CER-2 changes)
