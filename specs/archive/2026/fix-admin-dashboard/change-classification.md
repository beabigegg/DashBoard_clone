# Change Classification

## Change Types
- primary: bug-fix
- secondary: observability-enhancement, data-retention-policy-change

## Risk Level
- medium

## Impact Radius
- module-level (admin dashboard backend: log_store, login_session_store, admin_routes, duckdb_runtime, sync_worker)

## Tier
- 2

## Architecture Review Required
- no
- reason: All fixes are localized to existing modules; no module-boundary changes, no new contracts. Retention extension and TRUNCATE guard are operational/data-retention tweaks that fit within current architecture.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | |
| proposal.md | no | |
| spec.md | no | |
| design.md | no | architecture review not required; fixes are localized |
| qa-report.md | no | |
| regression-report.md | no | |
| visual-review-report.md | no | backend-only; no UI render changes |
| monkey-test-report.md | no | |
| stress-soak-report.md | no | |

## Required Contracts
- API: contracts/api/api-contract.md — additive only (new keys on `/admin/api/performance-detail`); no breaking change to `/admin/api/logs` or `/admin/api/user-usage-kpi`
- CSS/UI: none
- Env: contracts/env/env-contract.md — only if new tunable retention/threshold env vars are introduced
- Data shape: contracts/data/data-shape-contract.md — additive keys for performance-detail (`redis.evicted_keys`, `redis.expired_keys`, `redis.mem_fragmentation_ratio`, `redis.slowlog`, `duckdb.temp_dir_bytes`, `duckdb.memory_limit_state`)
- Business logic: none
- CI/CD: none

## Required Tests
- unit: log_store.query_logs_all (synced filter removed); login_session_store.cleanup_synced (retention boundary); admin_routes pagination merge-sort total-count + slice; duckdb_runtime telemetry helpers; sync_worker TRUNCATE-guard
- contract: /admin/api/performance-detail response keys present when Redis/DuckDB available; gracefully absent or null when not configured
- integration: admin log query end-to-end with SQLite-only and SQLite+MySQL merge; login session retention round-trip; performance-detail new keys
- E2E: none
- visual: none
- data-boundary: pagination edge cases (offset > total, page across merge boundary, empty MySQL result, empty SQLite result, both empty)
- resilience: MySQL unavailable graceful degrade; Redis SLOWLOG unavailable graceful degrade; DuckDB temp dir missing graceful degrade
- fuzz/monkey: none
- stress: none
- soak: none

## Required Agents
- contract-reviewer
- test-strategist
- ci-cd-gatekeeper
- implementation-planner
- backend-engineer
- qa-reviewer

## Inferred Acceptance Criteria
- AC-1: `log_store.query_logs_all()` returns both synced and unsynced log records (no `WHERE synced = 0` filter); `/admin/api/logs` exposes the full set ordered by timestamp desc, regardless of MySQL availability.
- AC-2: `login_session_store.cleanup_synced()` retains session records for the configured extended retention window (recommended 24h+); `/admin/api/user-usage-kpi` returns continuous history without gaps caused by physical deletion of synced rows.
- AC-3: `SyncWorker` startup migration only executes `TRUNCATE dashboard_login_sessions` when the target table is empty; re-deploy with existing rows does not wipe data.
- AC-4: `/admin/api/logs` pagination in merge mode returns the correct total count and correct slice for any (offset, limit); verified by data-boundary cases including offset > total, page across merge boundary, empty MySQL result, empty SQLite result.
- AC-5: `/admin/api/performance-detail` Redis section includes `evicted_keys`, `expired_keys`, `mem_fragmentation_ratio`, and `slowlog` (top-5) when Redis is reachable; gracefully omits/null-fills when unavailable.
- AC-6: `/admin/api/performance-detail` DuckDB section exposes `temp_dir_bytes` and `memory_limit_state`; gracefully degrades to null when unavailable.
- AC-7: All fixes degrade gracefully when MySQL is not configured — every endpoint returns well-formed responses backed by SQLite-only data; no 500s, no schema drift.

## Tasks Not Applicable
- not-applicable: 1.3, 2.4, 4.2

## Clarifications or Assumptions
- SQLite log retention extended from 1h to 24h (matching session retention target); final value goes into env-contract if it becomes tunable.
- DuckDB temp-dir threshold/alerting is out of scope; only raw metrics are exposed.
- New performance-detail JSON keys are purely additive; no existing key is renamed or removed.
- SyncWorker TRUNCATE-guard uses a `SELECT COUNT(*) LIMIT 1` check before executing TRUNCATE.

## Context Manifest Draft

### Affected Surfaces
- admin dashboard backend (log_store, login_session_store, admin_routes, duckdb_runtime, sync_worker)
- admin observability API surface (`/admin/api/logs`, `/admin/api/user-usage-kpi`, `/admin/api/performance-detail`)

### Allowed Paths
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

### Agent Work Packets

#### contract-reviewer
- specs/changes/fix-admin-dashboard/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- src/mes_dashboard/routes/admin_routes.py

#### test-strategist
- specs/changes/fix-admin-dashboard/
- src/mes_dashboard/core/log_store.py
- src/mes_dashboard/core/login_session_store.py
- src/mes_dashboard/core/sync_worker.py
- src/mes_dashboard/core/duckdb_runtime.py
- src/mes_dashboard/routes/admin_routes.py
- tests/test_admin_routes.py
- tests/test_admin_routes_logs.py
- tests/conftest.py

#### ci-cd-gatekeeper
- specs/changes/fix-admin-dashboard/
- .github/workflows/
- contracts/

#### implementation-planner
- specs/changes/fix-admin-dashboard/
- src/mes_dashboard/core/log_store.py
- src/mes_dashboard/core/login_session_store.py
- src/mes_dashboard/core/sync_worker.py
- src/mes_dashboard/core/duckdb_runtime.py
- src/mes_dashboard/routes/admin_routes.py

#### backend-engineer
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

#### qa-reviewer
- specs/changes/fix-admin-dashboard/
- src/mes_dashboard/core/log_store.py
- src/mes_dashboard/core/login_session_store.py
- src/mes_dashboard/core/sync_worker.py
- src/mes_dashboard/core/duckdb_runtime.py
- src/mes_dashboard/routes/admin_routes.py
- tests/

### Context Expansion Requests
- none at classification time
