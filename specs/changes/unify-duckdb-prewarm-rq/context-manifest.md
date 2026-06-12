# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- Spool/DuckDB caching architecture (resource_history, downtime_analysis)
- Shared spool warmup scheduler (_WARMUP_JOBS registry)
- Application startup orchestration (gunicorn preload/fork)
- RQ worker / queue infrastructure
- Env / business contracts (TTL semantics)

## Allowed Paths
- specs/changes/unify-duckdb-prewarm-rq/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/app.py
- src/mes_dashboard/core/spool_warmup_scheduler.py
- src/mes_dashboard/core/query_spool_store.py
- src/mes_dashboard/services/resource_history_duckdb_cache.py
- src/mes_dashboard/services/downtime_analysis_duckdb_cache.py
- src/mes_dashboard/services/downtime_analysis_cache.py
- src/mes_dashboard/services/resource_dataset_cache.py
- src/mes_dashboard/config/settings.py
- src/mes_dashboard/config/constants.py
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/CHANGELOG.md
- contracts/ci/ci-gate-contract.md
- docs/adr/0004-gunicorn-preload-app-fork-safety.md
- docs/cache-strategy.md
- tests/integration/test_preload_fork_safety.py
- tests/integration/_multi_worker_harness.py
- tests/integration/conftest.py
- tests/test_env_contract.py

## Required Contracts
- contracts/business/business-rules.md
- contracts/CHANGELOG.md
- contracts/env/env-contract.md (conditional on TTL becoming an env var)
- contracts/ci/ci-gate-contract.md (conditional on new gates)

## Required Tests
- tests/integration/test_preload_fork_safety.py
- tests/integration/_multi_worker_harness.py
- tests/integration/conftest.py
- tests/test_env_contract.py
- tests/ (resource_history + downtime_analysis cache unit test files — see CER-001)

## Agent Work Packets

### change-classifier
- specs/changes/unify-duckdb-prewarm-rq/
- specs/context/project-map.md
- specs/context/contracts-index.md

### spec-architect
- specs/changes/unify-duckdb-prewarm-rq/
- specs/context/project-map.md
- src/mes_dashboard/app.py
- src/mes_dashboard/core/spool_warmup_scheduler.py
- src/mes_dashboard/core/query_spool_store.py
- src/mes_dashboard/services/resource_history_duckdb_cache.py
- src/mes_dashboard/services/downtime_analysis_duckdb_cache.py
- src/mes_dashboard/services/downtime_analysis_cache.py
- src/mes_dashboard/services/resource_dataset_cache.py
- src/mes_dashboard/config/constants.py
- docs/adr/0004-gunicorn-preload-app-fork-safety.md
- docs/cache-strategy.md

### implementation-planner
- specs/changes/unify-duckdb-prewarm-rq/
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md

### backend-engineer
- specs/changes/unify-duckdb-prewarm-rq/
- src/mes_dashboard/app.py
- src/mes_dashboard/core/spool_warmup_scheduler.py
- src/mes_dashboard/core/query_spool_store.py
- src/mes_dashboard/services/resource_history_duckdb_cache.py
- src/mes_dashboard/services/downtime_analysis_duckdb_cache.py
- src/mes_dashboard/services/downtime_analysis_cache.py
- src/mes_dashboard/services/resource_dataset_cache.py
- src/mes_dashboard/config/constants.py
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/CHANGELOG.md
- tests/integration/test_preload_fork_safety.py
- tests/integration/_multi_worker_harness.py
- tests/integration/conftest.py
- tests/test_env_contract.py

### contract-reviewer
- specs/changes/unify-duckdb-prewarm-rq/
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/CHANGELOG.md
- contracts/ci/ci-gate-contract.md

### qa-reviewer
- specs/changes/unify-duckdb-prewarm-rq/
- src/mes_dashboard/app.py
- src/mes_dashboard/core/spool_warmup_scheduler.py
- tests/integration/test_preload_fork_safety.py
- tests/integration/_multi_worker_harness.py

## Context Expansion Requests
- request-id: CER-001
  requested_paths:
    - tests/
  reason: project-map.md truncated at cap=50; exact filenames for resource_history + downtime_analysis cache unit tests not confirmed by index
  status: pending

## Approved Expansions
-
