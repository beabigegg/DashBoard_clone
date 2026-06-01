# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- backend large-query pipeline (BatchQueryEngine + spool)
- per-service SQL decomposition (7 services)
- runtime env configuration (chunking flag + ENGINE_PARALLEL)

## Allowed Paths
- specs/changes/batch-rowcount-unification/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/services/batch_query_engine.py
- src/mes_dashboard/services/downtime_analysis_service.py
- src/mes_dashboard/services/downtime_analysis_cache.py
- src/mes_dashboard/services/production_history_service.py
- src/mes_dashboard/services/production_history_sql_runtime.py
- src/mes_dashboard/services/reject_dataset_cache.py
- src/mes_dashboard/services/reject_cache_sql_runtime.py
- src/mes_dashboard/services/resource_dataset_cache.py
- src/mes_dashboard/services/resource_history_sql_runtime.py
- src/mes_dashboard/services/hold_dataset_cache.py
- src/mes_dashboard/services/hold_history_sql_runtime.py
- src/mes_dashboard/services/job_query_service.py
- src/mes_dashboard/services/mid_section_defect_service.py
- src/mes_dashboard/services/msd_duckdb_runtime.py
- src/mes_dashboard/core/query_spool_store.py
- src/mes_dashboard/core/redis_df_store.py
- src/mes_dashboard/sql/downtime_analysis/
- src/mes_dashboard/sql/production_history/
- src/mes_dashboard/sql/reject_history/
- src/mes_dashboard/sql/hold_history/
- src/mes_dashboard/sql/job_query/
- src/mes_dashboard/sql/mid_section_defect/
- src/mes_dashboard/sql/resource/
- contracts/env/env-contract.md
- contracts/env/.env.example.template
- contracts/business/business-rules.md
- contracts/data/data-shape-contract.md
- contracts/CHANGELOG.md
- .env
- .env.development
- .env.production
- .env.example
- tests/

## Required Contracts
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/data/data-shape-contract.md (confirm-only)
- contracts/CHANGELOG.md

## Required Tests
- tests/test_batch_query_engine.py
- tests/ (per-service SQL-runtime unit tests, integration, resilience, stress/soak)

## Agent Work Packets

### spec-architect
- specs/changes/batch-rowcount-unification/
- specs/context/project-map.md
- src/mes_dashboard/services/batch_query_engine.py
- src/mes_dashboard/services/downtime_analysis_service.py
- src/mes_dashboard/core/query_spool_store.py
- src/mes_dashboard/sql/downtime_analysis/
- src/mes_dashboard/sql/production_history/
- src/mes_dashboard/sql/reject_history/
- src/mes_dashboard/sql/hold_history/
- src/mes_dashboard/sql/job_query/
- src/mes_dashboard/sql/mid_section_defect/
- src/mes_dashboard/sql/resource/
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/data/data-shape-contract.md

### implementation-planner
- specs/changes/batch-rowcount-unification/
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/data/data-shape-contract.md

### backend-engineer
- specs/changes/batch-rowcount-unification/
- src/mes_dashboard/services/batch_query_engine.py
- src/mes_dashboard/services/downtime_analysis_service.py
- src/mes_dashboard/services/downtime_analysis_cache.py
- src/mes_dashboard/services/production_history_service.py
- src/mes_dashboard/services/production_history_sql_runtime.py
- src/mes_dashboard/services/reject_dataset_cache.py
- src/mes_dashboard/services/reject_cache_sql_runtime.py
- src/mes_dashboard/services/resource_dataset_cache.py
- src/mes_dashboard/services/resource_history_sql_runtime.py
- src/mes_dashboard/services/hold_dataset_cache.py
- src/mes_dashboard/services/hold_history_sql_runtime.py
- src/mes_dashboard/services/job_query_service.py
- src/mes_dashboard/services/mid_section_defect_service.py
- src/mes_dashboard/services/msd_duckdb_runtime.py
- src/mes_dashboard/core/query_spool_store.py
- src/mes_dashboard/core/redis_df_store.py
- src/mes_dashboard/sql/downtime_analysis/
- src/mes_dashboard/sql/production_history/
- src/mes_dashboard/sql/reject_history/
- src/mes_dashboard/sql/hold_history/
- src/mes_dashboard/sql/job_query/
- src/mes_dashboard/sql/mid_section_defect/
- src/mes_dashboard/sql/resource/
- contracts/env/env-contract.md
- contracts/env/.env.example.template
- contracts/business/business-rules.md
- contracts/CHANGELOG.md
- .env
- .env.development
- .env.production
- .env.example
- tests/

### test-strategist
- specs/changes/batch-rowcount-unification/
- src/mes_dashboard/services/batch_query_engine.py
- src/mes_dashboard/sql/downtime_analysis/
- src/mes_dashboard/sql/production_history/
- src/mes_dashboard/sql/reject_history/
- src/mes_dashboard/sql/hold_history/
- src/mes_dashboard/sql/job_query/
- src/mes_dashboard/sql/mid_section_defect/
- src/mes_dashboard/sql/resource/
- tests/

### contract-reviewer
- specs/changes/batch-rowcount-unification/
- contracts/

### qa-reviewer
- specs/changes/batch-rowcount-unification/
- contracts/

## Context Expansion Requests

- request-id: CER-001
  requested_paths:
    - src/mes_dashboard/services/
  reason: project-map truncates services/ listing; exact filenames for resource_dataset_cache, reject_cache_sql_runtime, job_query_service confirmed from planning session
  status: approved

- request-id: CER-002
  requested_paths:
    - tests/
  reason: project-map truncates tests/ listing; per-service test filenames needed to extend rather than duplicate coverage
  status: approved

- request-id: CER-003
  requested_paths:
    - src/mes_dashboard/sql/
  reason: existing .sql filenames per service needed to name new count/paged SQL consistently; production_history count_query.sql confirmed as reusable
  status: approved

## Approved Expansions
- CER-001: src/mes_dashboard/services/ — approved; specific files listed in Allowed Paths above
- CER-002: tests/ — approved; listed in Allowed Paths above
- CER-003: src/mes_dashboard/sql/ — approved; subdirectories listed in Allowed Paths above
