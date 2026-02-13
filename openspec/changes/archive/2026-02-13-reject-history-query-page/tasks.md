## 1. Contract and Skeleton Setup

- [x] 1.1 Create backend blueprint scaffold `src/mes_dashboard/routes/reject_history_routes.py` and register it in `src/mes_dashboard/routes/__init__.py`
- [x] 1.2 Create service scaffold `src/mes_dashboard/services/reject_history_service.py` with SQL loader helpers
- [x] 1.3 Create frontend entry scaffold `frontend/src/reject-history/index.html`, `frontend/src/reject-history/main.js`, and `frontend/src/reject-history/App.vue`
- [x] 1.4 Add Vite input for `reject-history` in `frontend/vite.config.js`

## 2. SQL and Metric Semantics Implementation

- [x] 2.1 Finalize base query `src/mes_dashboard/sql/reject_history/performance_daily.sql` for five-reject-sum + defect separation
- [x] 2.2 Add API-specific SQL files in `src/mes_dashboard/sql/reject_history/` (summary, trend, reason_pareto, list, export)
- [x] 2.3 Implement `MOVEIN_QTY` dedupe by `HISTORYMAINLINEID` with deterministic fallback key
- [x] 2.4 Implement consistent rate calculations (`REJECT_RATE_PCT`, `DEFECT_RATE_PCT`, `REJECT_SHARE_PCT`) with zero-denominator handling
- [x] 2.5 Integrate `ERP_PJ_WIP_SCRAP_REASONS_EXCLUDE` policy mapping (`ENABLE_FLAG='Y'`) into reject-history aggregation flow
- [x] 2.6 Create `src/mes_dashboard/services/scrap_reason_exclusion_cache.py` with daily full-table refresh (Redis preferred + in-memory fallback)

## 3. Backend API Routes

- [x] 3.1 Implement `GET /api/reject-history/summary` with date/filter validation
- [x] 3.2 Implement `GET /api/reject-history/trend` with `granularity` validation (`day|week|month`)
- [x] 3.3 Implement `GET /api/reject-history/reason-pareto` with `metric_mode` validation (`reject_total|defect`)
- [x] 3.4 Implement `GET /api/reject-history/list` with paging bounds and reason/category filters
- [x] 3.5 Implement `GET /api/reject-history/export` and CSV output contract
- [x] 3.6 Apply configured rate limiting to list/export endpoints
- [x] 3.7 Add shared query param `include_excluded_scrap` (default false) and return effective policy mode in response meta

## 4. Frontend Visual and Interaction Implementation

- [x] 4.1 Build page header with title, data timestamp, and semantic badges for charge-off reject vs non-charge-off defect
- [x] 4.2 Build filter panel with required controls (`start_date/end_date`, reason, `WORKCENTER_GROUP`) plus query/clear actions, and wire it to all API calls
- [x] 4.3 Implement KPI card row (8 cards) with warm/cool semantic color lanes and zh-TW number formatting
- [x] 4.4 Implement dual trend charts (quantity trend + rate trend) using ECharts with synchronized date buckets
- [x] 4.5 Implement reason Pareto chart/table with `metric_mode` switch and cumulative percentage line, referencing WIP OVER VIEW interaction pattern
- [x] 4.6 Add Pareto mode toggle: default "top cumulative 80%" and optional "show all filtered categories"
- [x] 4.7 Implement detail table with pagination, active filter chips, and empty/error states
- [x] 4.8 Implement CSV export action using current filter context
- [x] 4.9 Add responsive rules so filter/cards/charts/table stay usable on tablet/mobile widths
- [x] 4.10 Add "納入不計良率報廢" toggle in filter panel and wire to all API calls + export

## 5. Shell and Route Governance Integration

- [x] 5.1 Add `/reject-history` contract entry to `frontend/src/portal-shell/routeContracts.js`
- [x] 5.2 Add `/reject-history` loader to `frontend/src/portal-shell/nativeModuleRegistry.js`
- [x] 5.3 Add `/reject-history` page metadata (drawer/order/status) to `data/page_status.json`
- [x] 5.4 Add Flask page route `/reject-history` using `send_from_directory` with dist fallback HTML

## 6. Tests and Quality Gates

- [x] 6.1 Add service tests in `tests/test_reject_history_service.py` covering formulas, dedupe, and edge cases
- [x] 6.2 Add route tests in `tests/test_reject_history_routes.py` covering validation, payload shape, and rate-limit behavior
- [x] 6.3 Add/extend route-contract parity and shell coverage tests for `/reject-history`
- [x] 6.4 Add frontend smoke/integration test for query flow and major visual sections
- [x] 6.5 Add exclusion-policy tests (`ENABLE_FLAG` handling, default exclude, include override, cache fallback path)

## 7. Documentation and Rollout

- [x] 7.1 Update implementation notes under `docs/reject_history_performance.md` to match API/UI field names
- [x] 7.2 Document exclusion-policy behavior and user toggle semantics in reject-history docs
- [x] 7.3 Document rollout policy (`dev` visibility first, then `released`) and rollback path
- [x] 7.4 Run end-to-end verification checklist and capture evidence before implementation handoff
