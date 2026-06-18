# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- Navigation shell (new "EAP" top-level category)
- EAP ALARM report page (new frontend feature app)
- Backend route + service + RQ worker (EAP spool pipeline)
- DuckDB spool-read compute + parquet namespace
- Oracle data access (DWH.EAP_EVENT, DWH.EAP_EVENT_DETAIL)
- Contracts: api, css, data, env, business, ci

## Allowed Paths
- specs/changes/eap-alarm-analysis/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/api/
- contracts/business/
- contracts/css/
- contracts/data/
- contracts/env/
- contracts/ci/
- src/mes_dashboard/routes/
- src/mes_dashboard/services/
- src/mes_dashboard/workers/
- src/mes_dashboard/core/
- src/mes_dashboard/app.py
- frontend/src/portal-shell/
- frontend/src/shared-ui/
- frontend/src/shared-composables/
- frontend/src/core/
- frontend/src/reject-history/
- frontend/src/styles/
- frontend/tailwind.config.js
- frontend/tests/
- tests/integration/
- tests/e2e/
- tests/contract/
- deploy/
- docs/adr/
- docs/architecture/cache-spool-patterns.md
- docs/architecture/service-patterns.md
- docs/migration/

## Required Contracts
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md

## Required Tests
- tests/integration/ (new test_eap_alarm_rq_async.py)
- tests/e2e/ (new test_eap_alarm_e2e.py)
- tests/contract/ (new EAP response samples)
- frontend/tests/ (new eap-alarm playwright spec + filter validation)

## Agent Work Packets

### spec-architect
- specs/changes/eap-alarm-analysis/
- contracts/api/
- contracts/data/
- contracts/business/
- contracts/env/
- src/mes_dashboard/workers/
- src/mes_dashboard/services/
- src/mes_dashboard/core/
- docs/adr/
- docs/architecture/cache-spool-patterns.md
- docs/architecture/service-patterns.md

### contract-reviewer
- specs/changes/eap-alarm-analysis/
- contracts/

### test-strategist
- specs/changes/eap-alarm-analysis/
- tests/integration/
- tests/e2e/
- tests/contract/
- frontend/tests/

### ci-cd-gatekeeper
- specs/changes/eap-alarm-analysis/
- contracts/ci/
- .github/
- deploy/

### implementation-planner
- specs/changes/eap-alarm-analysis/
- contracts/api/
- contracts/data/
- contracts/css/
- contracts/env/
- contracts/business/

### backend-engineer
- specs/changes/eap-alarm-analysis/
- contracts/api/
- contracts/data/
- contracts/business/
- contracts/env/
- src/mes_dashboard/routes/
- src/mes_dashboard/services/
- src/mes_dashboard/workers/
- src/mes_dashboard/core/
- src/mes_dashboard/app.py
- tests/integration/
- tests/contract/
- deploy/
- docs/architecture/cache-spool-patterns.md
- docs/architecture/service-patterns.md

### frontend-engineer
- specs/changes/eap-alarm-analysis/
- contracts/css/
- contracts/api/
- frontend/src/portal-shell/
- frontend/src/shared-ui/
- frontend/src/shared-composables/
- frontend/src/core/
- frontend/src/reject-history/
- frontend/src/styles/
- frontend/tailwind.config.js
- frontend/tests/
- docs/migration/

### e2e-resilience-engineer
- specs/changes/eap-alarm-analysis/
- tests/integration/
- tests/e2e/
- frontend/tests/
- src/mes_dashboard/workers/
- src/mes_dashboard/routes/

### ui-ux-reviewer
- specs/changes/eap-alarm-analysis/
- contracts/css/
- frontend/src/

### visual-reviewer
- specs/changes/eap-alarm-analysis/
- contracts/css/
- frontend/src/

### qa-reviewer
- specs/changes/eap-alarm-analysis/
- contracts/

## Context Expansion Requests

- request-id: CER-001
  requested_paths:
    - docs/adr/
    - docs/architecture/cache-spool-patterns.md
    - docs/architecture/service-patterns.md
  reason: Reference RQ+DuckDB spool-read pattern (reject-history) and known-pitfall rules (namespace registration, two-phase key resolution, parquet _SCHEMA_VERSION + rollback, SyncWorker guards) documented here; spec-architect needs these to write correct design.md and decide whether new ADR is warranted for JOIN-with-DETAIL shape.
  status: approved

## Approved Expansions
- docs/adr/ (CER-001, approved for spec-architect and backend-engineer)
- docs/architecture/cache-spool-patterns.md (CER-001, approved for spec-architect and backend-engineer)
- docs/architecture/service-patterns.md (CER-001, approved for spec-architect and backend-engineer)
- docs/migration/ (modernization-policy: frontend-engineer needs asset_readiness_manifest.json + route_scope_matrix.json)
