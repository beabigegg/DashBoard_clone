# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces

- Backend SQL: `src/mes_dashboard/sql/production_history/` (primarily `main_query.sql`; sibling filter/where templates if they reference dropped aggregated aliases)
- Backend service runtime: `src/mes_dashboard/services/production_history_sql_runtime.py` (`compute_detail_page`, `compute_matrix_view`, `stream_export`, `_build_filter_where`)
- Backend service / job: `src/mes_dashboard/services/production_history_service.py`, `production_history_job_service.py` (carry `PJ_FUNCTION` through; row-count expectations)
- Backend routes: `src/mes_dashboard/routes/production_history_routes.py` (response shape audit only)
- Frontend production-history app: `frontend/src/production-history/` (detail table column wiring; DuckDB consumer composable Matrix aggregation; CSV export wiring)
- Backend tests: production-history unit/integration/stress; parity fixtures
- Frontend tests: abort/legacy/validation
- Contracts: `contracts/data/data-shape-contract.md`, `contracts/business/business-rules.md`

## Allowed Paths
- specs/changes/prod-history-detail-raw-rows/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/data/
- contracts/business/
- contracts/api/
- contracts/ci/
- src/mes_dashboard/sql/production_history/
- src/mes_dashboard/sql/builder.py
- src/mes_dashboard/sql/filters.py
- src/mes_dashboard/sql/loader.py
- src/mes_dashboard/services/production_history_sql_runtime.py
- src/mes_dashboard/services/production_history_service.py
- src/mes_dashboard/services/production_history_job_service.py
- src/mes_dashboard/routes/production_history_routes.py
- src/mes_dashboard/core/query_spool_store.py
- src/mes_dashboard/core/spool_pipeline.py
- src/mes_dashboard/config/field_contracts.py
- shared/field_contracts.json
- frontend/src/production-history/
- frontend/src/core/field-contracts.ts
- frontend/src/core/endpoint-schemas.ts
- frontend/src/core/duckdb-client.ts
- frontend/src/core/types.ts
- frontend/tests/abort/production-history-abort.test.js
- frontend/tests/legacy/production-history.test.js
- frontend/tests/validation/useProductionHistory.validation.test.js
- tests/test_production_history_service.py
- tests/test_production_history_sql_runtime.py
- tests/test_production_history_routes.py
- tests/test_production_history_job_service.py
- tests/test_production_history_async_routes.py
- tests/test_frontend_compute_parity.py
- tests/test_frontend_duckdb_parity.py
- tests/fixtures/
- tests/e2e/test_production_history_e2e.py
- tests/stress/
- tests/integration/
- tests/conftest.py
- .github/workflows/

## Required Contracts
- contracts/data/data-shape-contract.md — production-history detail row schema (row-grain + `PJ_FUNCTION` + raw column names)
- contracts/business/business-rules.md — drop "first partial = original batch quantity" assumption; raw per-partial values

## Required Tests
- tests/test_production_history_sql_runtime.py — row-count + raw-column assertions
- tests/test_production_history_service.py — response shape (envelope unchanged)
- tests/test_production_history_routes.py — endpoint smoke
- tests/test_production_history_job_service.py — async job carries `PJ_FUNCTION`
- tests/test_frontend_compute_parity.py — fixture rebase for new row shape
- tests/test_frontend_duckdb_parity.py — fixture rebase + Matrix `COUNT(DISTINCT)` parity
- tests/e2e/test_production_history_e2e.py — multi-partial container renders multi-row
- tests/stress/<production-history stress> — p95 latency + parquet size delta
- frontend/tests/abort/production-history-abort.test.js — re-run, larger spool tolerated

## Agent Work Packets

### contract-reviewer
- specs/changes/prod-history-detail-raw-rows/
- contracts/data/
- contracts/business/
- contracts/api/

### test-strategist
- specs/changes/prod-history-detail-raw-rows/
- tests/
- frontend/tests/abort/
- frontend/tests/legacy/
- frontend/tests/validation/
- contracts/data/
- contracts/business/

### backend-engineer
- specs/changes/prod-history-detail-raw-rows/
- src/mes_dashboard/sql/production_history/
- src/mes_dashboard/sql/builder.py
- src/mes_dashboard/sql/filters.py
- src/mes_dashboard/sql/loader.py
- src/mes_dashboard/services/production_history_sql_runtime.py
- src/mes_dashboard/services/production_history_service.py
- src/mes_dashboard/services/production_history_job_service.py
- src/mes_dashboard/routes/production_history_routes.py
- src/mes_dashboard/core/query_spool_store.py
- src/mes_dashboard/core/spool_pipeline.py
- src/mes_dashboard/config/field_contracts.py
- shared/field_contracts.json
- contracts/data/
- contracts/business/
- tests/

### frontend-engineer
- specs/changes/prod-history-detail-raw-rows/
- frontend/src/production-history/
- frontend/src/core/field-contracts.ts
- frontend/src/core/endpoint-schemas.ts
- frontend/src/core/duckdb-client.ts
- frontend/src/core/types.ts
- shared/field_contracts.json
- contracts/data/
- frontend/tests/

### ci-cd-gatekeeper
- specs/changes/prod-history-detail-raw-rows/
- .github/workflows/

### qa-reviewer
- specs/changes/prod-history-detail-raw-rows/
- contracts/

## Context Expansion Requests

<!--
Agents must request context expansion instead of reading outside their work
packet. Format example for real requests:

- request-id: CER-001
  requested_paths:
    - src/example.ts
  reason: why this file is required
  status: pending
-->
-

## Approved Expansions
-
