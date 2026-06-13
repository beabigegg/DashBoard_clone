# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- backend-services (new job_registry.py; async_query_job_service.py dispatcher; 8 job service registrations)

## Allowed Paths
- specs/changes/job-registry-central/
- specs/context/project-map.md
- specs/context/contracts-index.md
- docs/dynamic-rq-migration-plan.md
- src/mes_dashboard/services/async_query_job_service.py
- src/mes_dashboard/services/job_registry.py
- src/mes_dashboard/services/reject_query_job_service.py
- src/mes_dashboard/services/yield_alert_job_service.py
- src/mes_dashboard/services/production_history_job_service.py
- src/mes_dashboard/services/trace_lineage_job_service.py
- src/mes_dashboard/services/msd_seed_job_service.py
- src/mes_dashboard/services/msd_lineage_job_service.py
- src/mes_dashboard/services/material_consumption_service.py
- src/mes_dashboard/services/material_trace_service.py
- tests/test_async_query_job_service.py
- tests/test_job_registry.py
- contracts/
- .github/workflows/

## Required Contracts
- none (contract-reviewer confirms no-change)

## Required Tests
- tests/test_async_query_job_service.py (no-regression)
- tests/test_job_registry.py (new, 5 tests)

## Agent Work Packets

### contract-reviewer
- specs/changes/job-registry-central/
- contracts/
- src/mes_dashboard/services/async_query_job_service.py

### test-strategist
- specs/changes/job-registry-central/
- tests/test_async_query_job_service.py

### ci-cd-gatekeeper
- specs/changes/job-registry-central/
- .github/workflows/

### implementation-planner
- specs/changes/job-registry-central/
- docs/dynamic-rq-migration-plan.md
- src/mes_dashboard/services/async_query_job_service.py

### backend-engineer
- specs/changes/job-registry-central/
- docs/dynamic-rq-migration-plan.md
- src/mes_dashboard/services/async_query_job_service.py
- src/mes_dashboard/services/reject_query_job_service.py
- src/mes_dashboard/services/yield_alert_job_service.py
- src/mes_dashboard/services/production_history_job_service.py
- src/mes_dashboard/services/trace_lineage_job_service.py
- src/mes_dashboard/services/msd_seed_job_service.py
- src/mes_dashboard/services/msd_lineage_job_service.py
- src/mes_dashboard/services/material_consumption_service.py
- src/mes_dashboard/services/material_trace_service.py
- tests/test_async_query_job_service.py
- tests/test_job_registry.py

### qa-reviewer
- specs/changes/job-registry-central/

## Context Expansion Requests
- none (CER-001 resolved: ls src/mes_dashboard/services/*job*.py confirmed all 8 service paths)

## Approved Expansions
-
