## 1. Contract and Skeleton Setup

- [ ] 1.1 Create backend blueprint scaffold `src/mes_dashboard/routes/reject_history_routes.py` and register it in `src/mes_dashboard/routes/__init__.py`
- [ ] 1.2 Create service scaffold `src/mes_dashboard/services/reject_history_service.py` with SQL loader helpers
- [ ] 1.3 Create frontend entry scaffold `frontend/src/reject-history/index.html`, `frontend/src/reject-history/main.js`, and `frontend/src/reject-history/App.vue`
- [ ] 1.4 Add Vite input for `reject-history` in `frontend/vite.config.js`

## 2. SQL and Metric Semantics Implementation

- [ ] 2.1 Finalize base query `src/mes_dashboard/sql/reject_history/performance_daily.sql` for five-reject-sum + defect separation
- [ ] 2.2 Add API-specific SQL files in `src/mes_dashboard/sql/reject_history/` (summary, trend, reason_pareto, list, export)
- [ ] 2.3 Implement `MOVEIN_QTY` dedupe by `HISTORYMAINLINEID` with deterministic fallback key
- [ ] 2.4 Implement consistent rate calculations (`REJECT_RATE_PCT`, `DEFECT_RATE_PCT`, `REJECT_SHARE_PCT`) with zero-denominator handling

## 3. Backend API Routes

- [ ] 3.1 Implement `GET /api/reject-history/summary` with date/filter validation
- [ ] 3.2 Implement `GET /api/reject-history/trend` with `granularity` validation (`day|week|month`)
- [ ] 3.3 Implement `GET /api/reject-history/reason-pareto` with `metric_mode` validation (`reject_total|defect`)
- [ ] 3.4 Implement `GET /api/reject-history/list` with paging bounds and reason/category filters
- [ ] 3.5 Implement `GET /api/reject-history/export` and CSV output contract
- [ ] 3.6 Apply configured rate limiting to list/export endpoints

## 4. Frontend Visual and Interaction Implementation

- [ ] 4.1 Build page header with title, data timestamp, and semantic badges for charge-off reject vs non-charge-off defect
- [ ] 4.2 Build filter panel (date range + dimensions + query/clear actions) and wire it to all API calls
- [ ] 4.3 Implement KPI card row (8 cards) with warm/cool semantic color lanes and zh-TW number formatting
- [ ] 4.4 Implement dual trend charts (quantity trend + rate trend) using ECharts with synchronized date buckets
- [ ] 4.5 Implement reason Pareto chart/table with `metric_mode` switch and cumulative percentage line
- [ ] 4.6 Implement detail table with pagination, active filter chips, and empty/error states
- [ ] 4.7 Implement CSV export action using current filter context
- [ ] 4.8 Add responsive rules so filter/cards/charts/table stay usable on tablet/mobile widths

## 5. Shell and Route Governance Integration

- [ ] 5.1 Add `/reject-history` contract entry to `frontend/src/portal-shell/routeContracts.js`
- [ ] 5.2 Add `/reject-history` loader to `frontend/src/portal-shell/nativeModuleRegistry.js`
- [ ] 5.3 Add `/reject-history` page metadata (drawer/order/status) to `data/page_status.json`
- [ ] 5.4 Add Flask page route `/reject-history` using `send_from_directory` with dist fallback HTML

## 6. Tests and Quality Gates

- [ ] 6.1 Add service tests in `tests/test_reject_history_service.py` covering formulas, dedupe, and edge cases
- [ ] 6.2 Add route tests in `tests/test_reject_history_routes.py` covering validation, payload shape, and rate-limit behavior
- [ ] 6.3 Add/extend route-contract parity and shell coverage tests for `/reject-history`
- [ ] 6.4 Add frontend smoke/integration test for query flow and major visual sections

## 7. Documentation and Rollout

- [ ] 7.1 Update implementation notes under `docs/reject_history_performance.md` to match API/UI field names
- [ ] 7.2 Document rollout policy (`dev` visibility first, then `released`) and rollback path
- [ ] 7.3 Run end-to-end verification checklist and capture evidence before implementation handoff
