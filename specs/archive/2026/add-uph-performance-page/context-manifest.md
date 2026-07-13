# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- Backend async report pipeline: new UPH service + worker (`BaseChunkedDuckDBJob`, TIME chunk), new spool namespace, new Oracle SQL
- Shared async infrastructure: global heavy-query semaphore, Oracle pool, RQ queue, `spool_routes._ALLOWED_NAMESPACES`, deploy services + dev launcher
- API surface: new UPH endpoints (view/trend, detail, filter-options)
- Frontend: new Vue app `frontend/src/uph-performance/` + portal-shell navigation/build/route wiring
- Runtime config: new `*_USE_UNIFIED_JOB` env flag
- Contracts: api, env, data, business, ci, css

## Allowed Paths
- specs/changes/add-uph-performance-page/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/api/
- contracts/env/
- contracts/data/
- contracts/business/
- contracts/ci/
- contracts/css/
- src/mes_dashboard/workers/
- src/mes_dashboard/services/
- src/mes_dashboard/routes/
- src/mes_dashboard/sql/
- src/mes_dashboard/core/
- src/mes_dashboard/config/
- deploy/
- scripts/
- frontend/src/uph-performance/
- frontend/src/portal-shell/
- frontend/src/eap-alarm/
- frontend/src/production-achievement/
- frontend/src/shared-composables/
- frontend/src/shared-ui/
- frontend/src/core/
- frontend/
- docs/architecture/eap-event-uph-collection-investigation.md
- docs/architecture/service-patterns.md
- docs/architecture/cache-spool-patterns.md
- docs/migration/full-modernization-architecture-blueprint/
- data/page_status.json
- tests/integration/
- tests/contract/
- tests/e2e/
- tests/stress/
- frontend/tests/

Note: `frontend/` is listed only for root config files (`vite.config.ts`, `tailwind.config.js`); implementation agents should read those config files plus their own feature subdirectory, not the whole tree.

## Required Contracts
- contracts/api/api-contract.md, contracts/api/api-inventory.md, contracts/api/openapi.json, contracts/openapi.json
- contracts/env/env-contract.md, contracts/env/env.schema.json, contracts/env/.env.example.template
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md
- contracts/css/css-contract.md, contracts/css/css-inventory.md

## Required Tests
- tests/integration/ (new `test_uph_*_rq_async.py`, semaphore/coarse-filter/data-boundary; templates: test_eap_alarm_rq_async.py, test_production_achievement_rq_async.py, test_base_job_semaphore_wiring.py)
- tests/contract/ (new response samples + schema coverage)
- tests/e2e/ (new UPH E2E; template test_eap_alarm_e2e.py)
- tests/stress/ (new `test_uph_*_stress.py`; templates test_production_achievement_stress.py, test_base_job_semaphore_stress.py) and soak via tests/integration/test_soak_workload.py
- frontend/tests/playwright/ (new `uph-performance.spec.ts`; template production-achievement-async.spec.ts) + navigation registration in frontend/tests/legacy/portal-shell-navigation.test.js

## Agent Work Packets

### spec-architect
- specs/changes/add-uph-performance-page/
- docs/architecture/eap-event-uph-collection-investigation.md
- docs/architecture/service-patterns.md
- docs/architecture/cache-spool-patterns.md
- contracts/business/
- contracts/data/
- contracts/env/
- contracts/ci/
- src/mes_dashboard/workers/
- src/mes_dashboard/services/
- src/mes_dashboard/core/
- src/mes_dashboard/sql/

### interaction-designer
- specs/changes/add-uph-performance-page/
- frontend/src/eap-alarm/
- frontend/src/production-achievement/
- contracts/css/

### implementation-planner
- specs/changes/add-uph-performance-page/
- contracts/api/
- contracts/env/
- contracts/data/
- contracts/business/
- contracts/ci/
- contracts/css/

### backend-engineer
- specs/changes/add-uph-performance-page/
- src/mes_dashboard/workers/
- src/mes_dashboard/services/
- src/mes_dashboard/routes/
- src/mes_dashboard/sql/
- src/mes_dashboard/core/
- src/mes_dashboard/config/
- deploy/
- scripts/
- contracts/api/
- contracts/env/
- contracts/data/
- contracts/business/
- contracts/ci/
- tests/integration/
- tests/contract/
- tests/e2e/
- docs/architecture/eap-event-uph-collection-investigation.md
- docs/architecture/service-patterns.md
- docs/architecture/cache-spool-patterns.md

### frontend-engineer
- specs/changes/add-uph-performance-page/
- frontend/src/uph-performance/
- frontend/src/portal-shell/
- frontend/src/eap-alarm/
- frontend/src/production-achievement/
- frontend/src/shared-composables/
- frontend/src/shared-ui/
- frontend/src/core/
- frontend/ (vite.config.ts, tailwind.config.js only)
- docs/migration/full-modernization-architecture-blueprint/
- data/page_status.json
- contracts/css/
- contracts/api/
- frontend/tests/

### test-strategist
- specs/changes/add-uph-performance-page/
- tests/integration/
- tests/contract/
- tests/e2e/
- tests/stress/
- frontend/tests/

### stress-soak-engineer
- specs/changes/add-uph-performance-page/
- tests/stress/
- tests/integration/
- src/mes_dashboard/core/
- src/mes_dashboard/workers/

### e2e-resilience-engineer
- specs/changes/add-uph-performance-page/
- tests/e2e/
- tests/integration/
- frontend/tests/

### ci-cd-gatekeeper
- specs/changes/add-uph-performance-page/
- deploy/
- scripts/
- contracts/ci/

### contract-reviewer / ui-ux-reviewer / visual-reviewer / qa-reviewer
- specs/changes/add-uph-performance-page/
- contracts/
- frontend/src/uph-performance/

## Context Expansion Requests
- request-id: CER-001
  requested_paths:
    - .github/workflows
  reason: wire the new frontend/tests/playwright/uph-performance.spec.ts into the playwright-critical-journeys CI job, per ci-gates.md's PR-blocking requirement (tasks.yml item 4.4)
  status: approved
## Approved Expansions
- .github/workflows
