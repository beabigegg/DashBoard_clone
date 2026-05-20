# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- backend report module: routes + service + sql + RQ worker (new material_consumption slice)
- two-layer cache pipeline: Redis + Parquet spool + DuckDB runtime
- frontend SPA: new material-consumption Vue app + echarts components
- portal-shell registration + route contracts
- admin-dashboard RQ monitoring (rq_monitor_service._QUEUE_NAMES)
- deploy: new systemd worker unit + watchdog
- startup-validated registration manifests (gunicorn crash risk)
- contracts: api, css, data, business, ci

## Allowed Paths
- specs/changes/material-part-consumption/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/error-format.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md
- src/mes_dashboard/routes/
- src/mes_dashboard/services/
- src/mes_dashboard/sql/
- src/mes_dashboard/workers/
- src/mes_dashboard/core/
- src/mes_dashboard/config/
- src/mes_dashboard/app.py
- data/page_status.json
- docs/migration/full-modernization-architecture-blueprint/
- frontend/src/material-consumption/
- frontend/src/shared-ui/
- frontend/src/shared-composables/
- frontend/src/core/
- frontend/src/portal-shell/
- frontend/src/styles/tailwind.css
- frontend/tailwind.config.js
- frontend/vite.config.ts
- frontend/tests/
- tests/
- deploy/
- .github/workflows/

## Required Contracts
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/error-format.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/ci/ci-gate-contract.md

## Required Tests
- tests/ (backend unit/contract/integration; mirror material_trace + production_history patterns)
- tests/stress/ (new material_consumption stress, nightly/weekly)
- frontend/tests/playwright/ (new E2E + data-boundary + resilience spec)
- frontend/tests/ (Vitest unit for new app/composables)

## Agent Work Packets

### change-classifier
- specs/changes/material-part-consumption/
- specs/context/project-map.md
- specs/context/contracts-index.md

### spec-architect
- specs/changes/material-part-consumption/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- src/mes_dashboard/services/
- src/mes_dashboard/core/
- src/mes_dashboard/sql/
- src/mes_dashboard/workers/

### contract-reviewer
- specs/changes/material-part-consumption/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/error-format.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md

### test-strategist
- specs/changes/material-part-consumption/
- tests/
- frontend/tests/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md

### ci-cd-gatekeeper
- specs/changes/material-part-consumption/
- contracts/ci/ci-gate-contract.md
- .github/workflows/
- deploy/

### implementation-planner
- specs/changes/material-part-consumption/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md

### backend-engineer
- specs/changes/material-part-consumption/
- src/mes_dashboard/routes/
- src/mes_dashboard/services/
- src/mes_dashboard/sql/
- src/mes_dashboard/workers/
- src/mes_dashboard/core/
- src/mes_dashboard/config/
- src/mes_dashboard/app.py
- data/page_status.json
- docs/migration/full-modernization-architecture-blueprint/
- deploy/
- .github/workflows/
- tests/

### frontend-engineer
- specs/changes/material-part-consumption/
- frontend/src/material-consumption/
- frontend/src/shared-ui/
- frontend/src/shared-composables/
- frontend/src/core/
- frontend/src/portal-shell/
- frontend/src/styles/tailwind.css
- frontend/tailwind.config.js
- frontend/vite.config.ts
- frontend/tests/

### ui-ux-reviewer
- specs/changes/material-part-consumption/
- frontend/src/material-consumption/
- frontend/src/portal-shell/
- contracts/css/css-contract.md
- contracts/css/css-inventory.md

### qa-reviewer
- specs/changes/material-part-consumption/
- contracts/
- tests/
- frontend/tests/
- deploy/
- .github/workflows/

## Context Expansion Requests

- request-id: CER-001
  requested_paths:
    - src/mes_dashboard/services/material_trace_service.py
    - src/mes_dashboard/services/material_trace_duckdb_runtime.py
    - src/mes_dashboard/services/resource_history_sql_runtime.py
  reason: spec-architect/backend-engineer need existing material-trace spool+DuckDB and resource-history granularity-regroup patterns as reference implementations
  status: approved

- request-id: CER-002
  requested_paths:
    - src/mes_dashboard/services/rq_monitor_service.py
  reason: backend-engineer must update hardcoded _QUEUE_NAMES list
  status: approved

- request-id: CER-003
  requested_paths:
    - (live Oracle) DESCRIBE DWH.DW_MES_CONTAINER
  reason: TYPE column name unresolved; design blocker — spec-architect must resolve before SQL written
  status: resolved — column is PJ_TYPE (VARCHAR2), same PJ_ naming convention as PJ_BOP and PJ_FUNCTION

## Approved Expansions
- CER-001: approved (files are within allowed src/mes_dashboard/services/ directory)
- CER-002: approved (file is within allowed src/mes_dashboard/services/ directory)
- CER-003: resolved — DWH.DW_MES_CONTAINER.PJ_TYPE (VARCHAR2) confirmed via live DESCRIBE
