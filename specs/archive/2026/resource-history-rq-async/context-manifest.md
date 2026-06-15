# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- backend route: resource-history query endpoint (sync/async branch)
- backend service/worker: resource-history async job service + BatchQueryEngine interaction + Parquet spool
- worker process registration / deployment config
- frontend: resource-history app async polling integration
- contracts: api, api-inventory, env, business
- tests: integration / e2e / stress / soak for the async path

## Allowed Paths
- specs/changes/resource-history-rq-async/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/api/
- contracts/env/
- contracts/business/
- contracts/data/
- contracts/ci/
- contracts/CHANGELOG.md
- src/mes_dashboard/routes/
- src/mes_dashboard/services/
- src/mes_dashboard/core/
- src/mes_dashboard/config/
- src/mes_dashboard/sql/resource_history/
- src/mes_dashboard/sql/resource/
- frontend/src/resource-history/
- frontend/src/shared-composables/
- frontend/src/core/
- scripts/
- deploy/
- supervisord.conf
- gunicorn.conf.py
- docs/adr/
- docs/architecture/
- tests/
- .env.example

## Required Contracts
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/CHANGELOG.md
- (conditional) contracts/data/data-shape-contract.md — only if async Parquet spool schema diverges from sync response

## Required Tests
- tests/integration/test_resource_history_rq_async.py (new)
- tests/integration/test_hold_history_rq_async.py (reference)
- tests/integration/test_downtime_rq_async.py (reference)
- tests/stress/test_resource_history_stress.py
- tests/test_api_contract.py
- frontend/tests/playwright/ (new resource-history async spec)

## Agent Work Packets

### spec-architect
- specs/changes/resource-history-rq-async/
- specs/context/project-map.md
- specs/context/contracts-index.md
- docs/adr/
- docs/architecture/
- src/mes_dashboard/routes/
- src/mes_dashboard/services/
- contracts/api/
- contracts/env/
- contracts/business/

### test-strategist
- specs/changes/resource-history-rq-async/
- tests/
- frontend/tests/
- contracts/api/
- contracts/env/

### ci-cd-gatekeeper
- specs/changes/resource-history-rq-async/
- contracts/ci/
- .github/workflows/
- scripts/
- supervisord.conf
- deploy/

### contract-reviewer
- specs/changes/resource-history-rq-async/
- contracts/
- .env.example

### implementation-planner
- specs/changes/resource-history-rq-async/
- contracts/api/
- contracts/env/
- contracts/business/
- src/mes_dashboard/routes/
- src/mes_dashboard/services/
- frontend/src/resource-history/
- tests/

### backend-engineer
- specs/changes/resource-history-rq-async/
- contracts/api/
- contracts/env/
- contracts/business/
- contracts/data/
- contracts/CHANGELOG.md
- src/mes_dashboard/routes/
- src/mes_dashboard/services/
- src/mes_dashboard/core/
- src/mes_dashboard/config/
- src/mes_dashboard/sql/resource_history/
- src/mes_dashboard/sql/resource/
- scripts/
- deploy/
- supervisord.conf
- gunicorn.conf.py
- tests/
- .env.example

### frontend-engineer
- specs/changes/resource-history-rq-async/
- frontend/src/resource-history/
- frontend/src/shared-composables/
- frontend/src/core/
- frontend/tests/

### e2e-resilience-engineer
- specs/changes/resource-history-rq-async/
- tests/e2e/
- tests/integration/
- frontend/tests/playwright/

### stress-soak-engineer
- specs/changes/resource-history-rq-async/
- tests/stress/
- tests/integration/
- scripts/

### qa-reviewer
- specs/changes/resource-history-rq-async/
- contracts/

## Context Expansion Requests

- request-id: CER-001
  requested_paths:
    - src/mes_dashboard/routes/resource_history_routes.py
    - src/mes_dashboard/routes/resource_routes.py
  reason: Project map lists BOTH resource_history_routes.py and resource_routes.py. The exact module that owns the resource-history POST query endpoint (which must gain the sync/async branch) must be confirmed before implementation.
  status: approved

- request-id: CER-002
  requested_paths:
    - src/mes_dashboard/services/
  reason: The services directory is truncated in project-map. The async worker module name (assumed resource_query_job_service.py) and the existing resource-history service module name are unconfirmed; need to confirm whether they exist or must be created, mirroring hold_query_job_service.py / downtime_query_job_service.py.
  status: approved

- request-id: CER-003
  requested_paths:
    - specs/archive/2026/hold-history-rq-async/
  reason: The reference implementation (hold-history-rq-async) is archived. Reading its design.md, implementation-plan.md, and contract diffs is the fastest way to mirror the established pattern accurately.
  status: approved

## Approved Expansions
- CER-001: src/mes_dashboard/routes/resource_history_routes.py and src/mes_dashboard/routes/resource_routes.py
- CER-002: src/mes_dashboard/services/ (all files)
- CER-003: specs/archive/2026/hold-history-rq-async/ (design.md, implementation-plan.md, archive.md)
