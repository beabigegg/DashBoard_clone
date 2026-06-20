# Context Manifest: rq-semaphore-wiring

## Affected Surfaces
- RQ async workers (Oracle-bound execute_*_job path): query_tool, hold, resource, reject
- Global concurrency control (core semaphore)
- Integration/stress concurrency test suites

## Allowed Paths
- specs/changes/rq-semaphore-wiring/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/core/global_concurrency.py
- src/mes_dashboard/core/heavy_query_telemetry.py
- src/mes_dashboard/services/query_tool_service.py
- src/mes_dashboard/services/hold_query_job_service.py
- src/mes_dashboard/services/resource_query_job_service.py
- src/mes_dashboard/services/reject_query_job_service.py
- docs/adr/0011-global-concurrency-semaphore-rq-oracle-bound.md
- docs/architecture/service-patterns.md
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md
- contracts/env/env-contract.md
- tests/integration/test_query_tool_rq_async.py
- tests/integration/test_wip_rowcount_rq_routing.py
- tests/integration/test_rq_semaphore_wiring.py
- tests/stress/test_query_tool_stress.py
- tests/stress/test_rq_semaphore_stress.py
- tests/test_rq_semaphore_wiring.py
- tests/test_global_concurrency.py

## Required Contracts
- contracts/business/business-rules.md (candidate: concurrency-bound rule)
- contracts/ci/ci-gate-contract.md (candidate: stress/soak gate)
- contracts/env/env-contract.md (read-only confirmation)

## Required Tests
- tests/integration/ (new multi-worker concurrency tests)
- tests/stress/ (concurrency burst + no-leak)

## Agent Work Packets

### spec-architect
- specs/changes/rq-semaphore-wiring/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/core/global_concurrency.py
- src/mes_dashboard/core/heavy_query_telemetry.py
- docs/adr/0011-global-concurrency-semaphore-rq-oracle-bound.md
- docs/architecture/service-patterns.md

### contract-reviewer
- specs/changes/rq-semaphore-wiring/
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md
- contracts/env/env-contract.md

### test-strategist
- specs/changes/rq-semaphore-wiring/
- tests/integration/test_query_tool_rq_async.py
- tests/stress/test_query_tool_stress.py

### ci-cd-gatekeeper
- specs/changes/rq-semaphore-wiring/
- contracts/ci/ci-gate-contract.md

### implementation-planner
- specs/changes/rq-semaphore-wiring/
- src/mes_dashboard/core/global_concurrency.py
- src/mes_dashboard/services/query_tool_service.py
- src/mes_dashboard/services/hold_query_job_service.py
- src/mes_dashboard/services/resource_query_job_service.py
- src/mes_dashboard/services/reject_query_job_service.py
- docs/architecture/service-patterns.md

### backend-engineer
- specs/changes/rq-semaphore-wiring/
- src/mes_dashboard/core/global_concurrency.py
- src/mes_dashboard/services/query_tool_service.py
- src/mes_dashboard/services/hold_query_job_service.py
- src/mes_dashboard/services/resource_query_job_service.py
- src/mes_dashboard/services/reject_query_job_service.py

### stress-soak-engineer
- specs/changes/rq-semaphore-wiring/
- tests/stress/test_query_tool_stress.py
- tests/integration/test_query_tool_rq_async.py

### qa-reviewer
- specs/changes/rq-semaphore-wiring/

## Context Expansion Requests
- (none pending; CER-001 and CER-002 resolved before manifest was written)

## Approved Expansions
- CER-001: src/mes_dashboard/services/resource_query_job_service.py, src/mes_dashboard/services/reject_query_job_service.py — confirmed to exist; added to Allowed Paths.
- CER-002: src/mes_dashboard/core/heavy_query_telemetry.py — confirmed to exist; added for spec-architect if acquire boundary touches telemetry.
