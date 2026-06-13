# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- API route: downtime-analysis query (sync/async branch)
- New backend service + RQ worker fn (downtime-query queue)
- Job-registry dispatcher (Phase 2 plumbing)
- Frontend downtime-analysis app + shared async-polling composable
- Contracts: api, env, data, business, ci
- Deploy: new downtime worker systemd unit + gunicorn config

## Allowed Paths
- specs/changes/downtime-rq-async/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md
- src/mes_dashboard/routes/downtime_analysis_routes.py
- src/mes_dashboard/services/downtime_analysis_service.py
- src/mes_dashboard/services/downtime_analysis_cache.py
- src/mes_dashboard/services/downtime_analysis_duckdb_cache.py
- src/mes_dashboard/services/downtime_query_job_service.py
- src/mes_dashboard/services/async_query_job_service.py
- src/mes_dashboard/services/job_registry.py
- src/mes_dashboard/workers/
- frontend/src/downtime-analysis/App.vue
- frontend/src/downtime-analysis/composables/
- frontend/src/shared-ui/components/AsyncQueryProgress.vue
- frontend/src/shared-composables/useAsyncJobPolling.ts
- docs/adr/0003-downtime-rowcount-chunking-exclusion.md
- docs/adr/0007-downtime-browser-duckdb-compute-relocation.md
- deploy/
- gunicorn.conf.py
- .env.example
- tests/test_downtime_analysis_service.py
- tests/integration/
- tests/e2e/test_downtime_analysis_e2e.py
- frontend/tests/playwright/downtime-analysis.spec.js

## Required Contracts
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md

## Required Tests
- tests/test_downtime_analysis_service.py
- tests/integration/
- tests/e2e/test_downtime_analysis_e2e.py
- frontend/tests/playwright/downtime-analysis.spec.js

## Agent Work Packets

### spec-architect
- specs/changes/downtime-rq-async/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md
- docs/adr/0003-downtime-rowcount-chunking-exclusion.md
- docs/adr/0007-downtime-browser-duckdb-compute-relocation.md
- src/mes_dashboard/services/downtime_analysis_service.py
- src/mes_dashboard/services/async_query_job_service.py
- src/mes_dashboard/services/job_registry.py

### implementation-planner
- specs/changes/downtime-rq-async/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md

### backend-engineer
- specs/changes/downtime-rq-async/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- src/mes_dashboard/routes/downtime_analysis_routes.py
- src/mes_dashboard/services/downtime_analysis_service.py
- src/mes_dashboard/services/downtime_analysis_cache.py
- src/mes_dashboard/services/downtime_analysis_duckdb_cache.py
- src/mes_dashboard/services/downtime_query_job_service.py
- src/mes_dashboard/services/async_query_job_service.py
- src/mes_dashboard/services/job_registry.py
- src/mes_dashboard/workers/
- .env.example
- tests/test_downtime_analysis_service.py
- tests/integration/

### frontend-engineer
- specs/changes/downtime-rq-async/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- frontend/src/downtime-analysis/App.vue
- frontend/src/downtime-analysis/composables/
- frontend/src/shared-ui/components/AsyncQueryProgress.vue
- frontend/src/shared-composables/useAsyncJobPolling.ts
- frontend/tests/playwright/downtime-analysis.spec.js

### test-strategist
- specs/changes/downtime-rq-async/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- src/mes_dashboard/services/downtime_query_job_service.py
- src/mes_dashboard/services/downtime_analysis_service.py
- tests/test_downtime_analysis_service.py
- tests/integration/
- tests/e2e/test_downtime_analysis_e2e.py
- frontend/tests/playwright/downtime-analysis.spec.js

### contract-reviewer
- specs/changes/downtime-rq-async/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md

### ui-ux-reviewer
- specs/changes/downtime-rq-async/
- frontend/src/downtime-analysis/App.vue
- frontend/src/shared-ui/components/AsyncQueryProgress.vue
- frontend/src/shared-composables/useAsyncJobPolling.ts

### ci-cd-gatekeeper
- specs/changes/downtime-rq-async/
- contracts/ci/ci-gate-contract.md
- contracts/env/env-contract.md
- deploy/
- gunicorn.conf.py
- .env.example

### e2e-resilience-engineer
- specs/changes/downtime-rq-async/
- contracts/api/api-contract.md
- src/mes_dashboard/services/downtime_query_job_service.py
- src/mes_dashboard/workers/
- tests/integration/
- tests/e2e/test_downtime_analysis_e2e.py
- frontend/tests/playwright/downtime-analysis.spec.js

### qa-reviewer
- specs/changes/downtime-rq-async/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md

## Context Expansion Requests

- request-id: CER-001
  requested_paths:
    - frontend/src/downtime-analysis/composables/
  reason: project-map truncates the downtime-analysis composables directory; frontend-engineer needs the exact composable that owns query dispatch to wire the 202/polling branch
  status: approved

- request-id: CER-002
  requested_paths:
    - deploy/
    - gunicorn.conf.py
  reason: ci-cd-gatekeeper needs the existing worker systemd units and gunicorn config as template for the new downtime-query worker
  status: approved

## Approved Expansions
- frontend/src/downtime-analysis/composables/ (CER-001: approved 2026-06-13)
- deploy/ (CER-002: approved 2026-06-13)
- gunicorn.conf.py (CER-002: approved 2026-06-13)
