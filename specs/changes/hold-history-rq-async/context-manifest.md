# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- backend: hold-history async query path (service + route + worker)
- shared async infrastructure: job registry / enqueue / register_job_type
- frontend: hold-history app (progress integration)
- runtime config: HOLD_* env vars
- delivery: hold-history RQ queue + systemd worker unit + CI gates

## Allowed Paths
- specs/changes/hold-history-rq-async/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/env/env-contract.md
- contracts/ci/ci-gate-contract.md
- contracts/data/data-shape-contract.md
- src/mes_dashboard/services/hold_history_service.py
- src/mes_dashboard/services/hold_history_sql_runtime.py
- src/mes_dashboard/services/hold_dataset_cache.py
- src/mes_dashboard/services/batch_query_engine.py
- src/mes_dashboard/services/job_registry.py
- src/mes_dashboard/services/async_query_job_service.py
- src/mes_dashboard/services/downtime_query_job_service.py
- src/mes_dashboard/services/production_history_job_service.py
- src/mes_dashboard/services/hold_query_job_service.py
- src/mes_dashboard/routes/hold_history_routes.py
- src/mes_dashboard/app.py
- src/mes_dashboard/workers/
- src/mes_dashboard/services/rq_monitor_service.py
- frontend/src/hold-history/
- frontend/src/shared-composables/useAsyncJobPolling.ts
- frontend/src/shared-ui/
- frontend/tests/playwright/hold-history-flat-table.spec.js
- tests/test_hold_history_routes.py
- tests/test_hold_history_service.py
- tests/test_batch_query_engine.py
- tests/test_rq_monitor_service.py
- tests/integration/test_downtime_rq_async.py
- tests/integration/test_hold_history_rq_async.py
- tests/e2e/test_hold_history_e2e.py
- deploy/
- .env.example
- docs/dynamic-rq-migration-plan.md
- docs/adr/0003-downtime-rowcount-chunking-exclusion.md

## Required Contracts
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/env/env-contract.md
- contracts/ci/ci-gate-contract.md

## Required Tests
- tests/test_hold_history_routes.py
- tests/test_hold_history_service.py
- tests/integration/test_hold_history_rq_async.py
- tests/e2e/test_hold_history_e2e.py
- frontend/tests/playwright/hold-history-flat-table.spec.js

## Agent Work Packets

### implementation-planner
- specs/changes/hold-history-rq-async/
- specs/context/project-map.md
- specs/context/contracts-index.md
- docs/dynamic-rq-migration-plan.md
- docs/adr/0003-downtime-rowcount-chunking-exclusion.md
- src/mes_dashboard/services/downtime_query_job_service.py
- src/mes_dashboard/services/production_history_job_service.py
- src/mes_dashboard/services/hold_history_service.py
- src/mes_dashboard/routes/hold_history_routes.py

### backend-engineer
- specs/changes/hold-history-rq-async/
- contracts/api/api-contract.md
- contracts/env/env-contract.md
- contracts/data/data-shape-contract.md
- src/mes_dashboard/services/hold_history_service.py
- src/mes_dashboard/services/hold_history_sql_runtime.py
- src/mes_dashboard/services/hold_dataset_cache.py
- src/mes_dashboard/services/batch_query_engine.py
- src/mes_dashboard/services/job_registry.py
- src/mes_dashboard/services/async_query_job_service.py
- src/mes_dashboard/services/downtime_query_job_service.py
- src/mes_dashboard/services/production_history_job_service.py
- src/mes_dashboard/services/hold_query_job_service.py
- src/mes_dashboard/routes/hold_history_routes.py
- src/mes_dashboard/app.py
- src/mes_dashboard/workers/
- src/mes_dashboard/services/rq_monitor_service.py
- tests/test_hold_history_routes.py
- tests/test_hold_history_service.py
- tests/test_batch_query_engine.py
- tests/test_rq_monitor_service.py
- tests/integration/test_downtime_rq_async.py
- tests/integration/test_hold_history_rq_async.py
- deploy/
- .env.example

### frontend-engineer
- specs/changes/hold-history-rq-async/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- frontend/src/hold-history/
- frontend/src/shared-composables/useAsyncJobPolling.ts
- frontend/src/shared-ui/
- frontend/tests/playwright/hold-history-flat-table.spec.js

### test-strategist
- specs/changes/hold-history-rq-async/
- contracts/api/api-contract.md
- contracts/env/env-contract.md
- tests/integration/test_downtime_rq_async.py
- tests/test_hold_history_service.py
- tests/test_hold_history_routes.py
- tests/e2e/test_hold_history_e2e.py

### contract-reviewer
- specs/changes/hold-history-rq-async/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/env/env-contract.md
- contracts/ci/ci-gate-contract.md
- contracts/data/data-shape-contract.md

### ci-cd-gatekeeper
- specs/changes/hold-history-rq-async/
- contracts/ci/ci-gate-contract.md
- contracts/env/env-contract.md
- deploy/
- .env.example
- src/mes_dashboard/workers/

### qa-reviewer
- specs/changes/hold-history-rq-async/
- contracts/api/api-contract.md
- contracts/env/env-contract.md
- contracts/ci/ci-gate-contract.md

## Context Expansion Requests

- request-id: CER-001
  requested_paths:
    - src/mes_dashboard/services/hold_history_service.py
  reason: project-map truncates services/ at cap=50; exact execute_primary_query() signature, BatchQueryEngine row-count chunking call site must be confirmed before milestone placement
  status: approved

## Approved Expansions
- src/mes_dashboard/services/hold_history_service.py (CER-001: approved 2026-06-13)
