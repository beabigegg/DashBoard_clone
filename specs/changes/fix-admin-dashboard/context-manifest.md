# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- admin dashboard backend (log_store, login_session_store, admin_routes, duckdb_runtime, sync_worker)
- admin observability API surface (`/admin/api/logs`, `/admin/api/user-usage-kpi`, `/admin/api/performance-detail`)

## Allowed Paths
- specs/changes/fix-admin-dashboard/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/core/log_store.py
- src/mes_dashboard/core/login_session_store.py
- src/mes_dashboard/core/sync_worker.py
- src/mes_dashboard/core/duckdb_runtime.py
- src/mes_dashboard/core/mysql_client.py
- src/mes_dashboard/core/redis_client.py
- src/mes_dashboard/routes/admin_routes.py
- src/mes_dashboard/core/response.py
- src/mes_dashboard/app.py
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- tests/test_admin_routes.py
- tests/test_admin_routes_logs.py
- tests/conftest.py

## Required Contracts
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md (only if new env vars are added)

## Required Tests
- tests/test_admin_routes.py
- tests/test_admin_routes_logs.py
- (new) tests/test_log_store.py
- (new) tests/test_login_session_store.py
- (new) tests/test_duckdb_runtime_telemetry.py

## Agent Work Packets

### contract-reviewer
- specs/changes/fix-admin-dashboard/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- src/mes_dashboard/routes/admin_routes.py

### test-strategist
- specs/changes/fix-admin-dashboard/
- src/mes_dashboard/core/log_store.py
- src/mes_dashboard/core/login_session_store.py
- src/mes_dashboard/core/sync_worker.py
- src/mes_dashboard/core/duckdb_runtime.py
- src/mes_dashboard/routes/admin_routes.py
- tests/test_admin_routes.py
- tests/test_admin_routes_logs.py
- tests/conftest.py

### ci-cd-gatekeeper
- specs/changes/fix-admin-dashboard/
- .github/workflows/
- contracts/

### implementation-planner
- specs/changes/fix-admin-dashboard/
- src/mes_dashboard/core/log_store.py
- src/mes_dashboard/core/login_session_store.py
- src/mes_dashboard/core/sync_worker.py
- src/mes_dashboard/core/duckdb_runtime.py
- src/mes_dashboard/routes/admin_routes.py

### backend-engineer
- specs/changes/fix-admin-dashboard/
- src/mes_dashboard/core/log_store.py
- src/mes_dashboard/core/login_session_store.py
- src/mes_dashboard/core/sync_worker.py
- src/mes_dashboard/core/duckdb_runtime.py
- src/mes_dashboard/core/mysql_client.py
- src/mes_dashboard/core/redis_client.py
- src/mes_dashboard/routes/admin_routes.py
- src/mes_dashboard/core/response.py
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- tests/test_admin_routes.py
- tests/test_admin_routes_logs.py
- tests/conftest.py

### qa-reviewer
- specs/changes/fix-admin-dashboard/
- src/mes_dashboard/core/log_store.py
- src/mes_dashboard/core/login_session_store.py
- src/mes_dashboard/core/sync_worker.py
- src/mes_dashboard/core/duckdb_runtime.py
- src/mes_dashboard/routes/admin_routes.py
- tests/

## Context Expansion Requests
-

## Approved Expansions
-
