# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- gunicorn process model / worker lifecycle (master pre-fork + worker post_fork hooks)
- Oracle connection pool (SQLAlchemy engine) reinit after fork
- Redis connection pool / RQ client reinit after fork
- SQLite-backed stores (log_store, login_session_store, metrics_history) handle reinit after fork
- Background thread fleet (cache_updater, realtime_equipment_cache, scrap_reason_exclusion_cache, metrics_history, worker_memory_guard, anomaly_detection_scheduler, keep-alive, query_spool_store cleanup) restart per worker
- Single-run cache/prewarm services (downtime_analysis_cache, material_consumption_service, resource_history_duckdb_cache, resource_cache)
- CI multi-worker / concurrency integration gates

## Allowed Paths
- specs/changes/gunicorn-preload-workers/
- specs/context/project-map.md
- specs/context/contracts-index.md
- gunicorn.conf.py
- src/mes_dashboard/app.py
- src/mes_dashboard/__main__.py
- src/mes_dashboard/rq_worker_preload.py
- src/mes_dashboard/config/database.py
- src/mes_dashboard/config/settings.py
- src/mes_dashboard/core/database.py
- src/mes_dashboard/core/redis_client.py
- src/mes_dashboard/core/redis_df_store.py
- src/mes_dashboard/core/cache_updater.py
- src/mes_dashboard/core/cache.py
- src/mes_dashboard/core/cache_plane.py
- src/mes_dashboard/core/log_store.py
- src/mes_dashboard/core/login_session_store.py
- src/mes_dashboard/core/metrics_history.py
- src/mes_dashboard/core/metrics.py
- src/mes_dashboard/core/worker_memory_guard.py
- src/mes_dashboard/core/query_spool_store.py
- src/mes_dashboard/core/spool_warmup_scheduler.py
- src/mes_dashboard/core/spool_pipeline.py
- src/mes_dashboard/core/spool_dir_check.py
- src/mes_dashboard/core/sync_worker.py
- src/mes_dashboard/core/runtime_contract.py
- src/mes_dashboard/services/downtime_analysis_cache.py
- src/mes_dashboard/services/material_consumption_service.py
- src/mes_dashboard/services/resource_cache.py
- src/mes_dashboard/services/resource_history_duckdb_cache.py
- src/mes_dashboard/services/realtime_equipment_cache.py
- src/mes_dashboard/services/reason_filter_cache.py
- src/mes_dashboard/services/container_filter_cache.py
- src/mes_dashboard/services/anomaly_detection_scheduler.py
- src/mes_dashboard/services/scrap_reason_exclusion_cache.py
- contracts/ci/ci-gate-contract.md
- contracts/env/env-contract.md
- contracts/CHANGELOG.md
- tests/integration/
- tests/test_app_factory.py
- tests/test_cache_updater.py
- tests/test_cache_updater_lock_behavior.py
- tests/test_cache_lifecycle.py
- tests/test_cross_worker_result_sharing.py
- tests/e2e/test_global_connection.py
- tests/e2e/test_cache_e2e.py
- tests/e2e/test_resource_cache_e2e.py
- tests/e2e/test_realtime_equipment_e2e.py
- tests/conftest.py
- .github/workflows/backend-tests.yml
- .github/workflows/soak-tests.yml
- .github/workflows/stress-tests.yml
- .github/workflows/measure-stability.yml
- .github/workflows/released-pages-hardening-gates.yml
- docs/adr/

## Required Contracts
- contracts/ci/ci-gate-contract.md — update required
- contracts/env/env-contract.md — conditional (only if a new env var is introduced; architect decides in design.md)
- contracts/CHANGELOG.md — version entry for any contract that changes

## Required Tests
- tests/integration/ (multi-worker, concurrency, resilience, soak)
- tests/test_app_factory.py
- tests/e2e/ (startup/connection smoke)

## Agent Work Packets

### spec-architect
- specs/changes/gunicorn-preload-workers/
- specs/context/project-map.md
- specs/context/contracts-index.md
- gunicorn.conf.py
- src/mes_dashboard/app.py
- src/mes_dashboard/core/database.py
- src/mes_dashboard/core/redis_client.py
- src/mes_dashboard/services/resource_cache.py
- src/mes_dashboard/services/resource_history_duckdb_cache.py
- src/mes_dashboard/services/downtime_analysis_cache.py
- contracts/ci/ci-gate-contract.md
- contracts/env/env-contract.md
- docs/adr/

### implementation-planner
- specs/changes/gunicorn-preload-workers/
- specs/context/project-map.md
- gunicorn.conf.py
- src/mes_dashboard/app.py
- src/mes_dashboard/core/
- src/mes_dashboard/config/
- src/mes_dashboard/services/resource_cache.py
- src/mes_dashboard/services/resource_history_duckdb_cache.py
- src/mes_dashboard/services/downtime_analysis_cache.py
- src/mes_dashboard/services/material_consumption_service.py
- tests/integration/

### bug-fix-engineer
- specs/changes/gunicorn-preload-workers/
- gunicorn.conf.py
- src/mes_dashboard/app.py
- src/mes_dashboard/core/database.py
- src/mes_dashboard/core/redis_client.py
- src/mes_dashboard/core/cache_updater.py
- src/mes_dashboard/services/resource_cache.py
- src/mes_dashboard/services/resource_history_duckdb_cache.py
- src/mes_dashboard/services/downtime_analysis_cache.py
- src/mes_dashboard/services/material_consumption_service.py
- tests/integration/
- tests/test_cache_updater_lock_behavior.py

### backend-engineer
- specs/changes/gunicorn-preload-workers/
- gunicorn.conf.py
- src/mes_dashboard/app.py
- src/mes_dashboard/__main__.py
- src/mes_dashboard/config/database.py
- src/mes_dashboard/core/
- src/mes_dashboard/services/resource_cache.py
- src/mes_dashboard/services/resource_history_duckdb_cache.py
- src/mes_dashboard/services/downtime_analysis_cache.py
- src/mes_dashboard/services/material_consumption_service.py
- src/mes_dashboard/services/realtime_equipment_cache.py
- src/mes_dashboard/services/scrap_reason_exclusion_cache.py
- src/mes_dashboard/services/anomaly_detection_scheduler.py
- tests/

### test-strategist
- specs/changes/gunicorn-preload-workers/
- tests/integration/
- tests/e2e/
- tests/test_app_factory.py
- contracts/env/env-contract.md
- contracts/ci/ci-gate-contract.md

### contract-reviewer
- specs/changes/gunicorn-preload-workers/
- contracts/

### qa-reviewer
- specs/changes/gunicorn-preload-workers/
- contracts/ci/ci-gate-contract.md
- tests/integration/
- .github/workflows/

## Context Expansion Requests

## Approved Expansions

- request-id: CER-001
  approved_paths:
    - src/mes_dashboard/services/resource_history_duckdb_cache.py
  reason: Named in change-request as the broken file-lock/deadlock module; path confirmed to exist.
  status: approved

- request-id: CER-002
  approved_paths:
    - src/mes_dashboard/services/scrap_reason_exclusion_cache.py
    - src/mes_dashboard/core/spool_pipeline.py
    - src/mes_dashboard/core/spool_dir_check.py
  reason: Background-thread / spool-init subsystems whose post-fork restart placement must be decided; paths confirmed to exist.
  status: approved

- request-id: CER-003
  approved_paths:
    - .github/workflows/measure-stability.yml
    - .github/workflows/released-pages-hardening-gates.yml
  reason: CI workflow scoping for which workflows must carry the new multi-worker gate; paths confirmed to exist.
  status: approved
