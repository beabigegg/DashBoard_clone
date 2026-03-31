## 1. Backend Unit Test Gap-Fill

- [x] 1.1 Create `tests/test_sql_fragments.py` — test SQL fragment generation functions
- [x] 1.2 Create `tests/test_user_usage_kpi_service.py` — test user usage KPI aggregation logic
- [x] 1.3 Create `tests/test_anomaly_detection_sql_runtime.py` — test anomaly SQL query building
- [x] 1.4 Create `tests/test_material_trace_duckdb_runtime.py` — test material trace DuckDB compute
- [x] 1.5 Create `tests/test_yield_alert_sql_runtime.py` — test yield alert SQL runtime queries
- [x] 1.6 Create `tests/test_reject_cache_sql_runtime.py` — test reject cache SQL runtime queries
- [x] 1.7 Create `tests/test_resource_history_sql_runtime.py` — test resource history SQL runtime
- [x] 1.8 Create `tests/test_hold_history_sql_runtime.py` — test hold history SQL runtime queries
- [x] 1.9 Create `tests/test_production_history_sql_runtime.py` — test production history SQL runtime
- [x] 1.10 Create `tests/test_ai_business_context.py` — test AI business context loading and formatting
- [x] 1.11 Create `tests/test_navigation_contract.py` — test navigation contract validation logic
- [x] 1.12 Create `tests/test_yield_alert_contracts.py` — test yield alert contract assertions
- [x] 1.13 Create `tests/test_dashboard_service.py` — test dashboard aggregation service

## 2. Backend Integration Test Gap-Fill

- [x] 2.1 Create `tests/test_dashboard_routes.py` — integration tests for dashboard route endpoints
- [x] 2.2 Create `tests/test_spool_routes.py` — integration tests for spool/cache route endpoints
- [x] 2.3 Expand `tests/test_admin_routes.py` — add coverage for any untested admin endpoints
- [x] 2.4 Audit all existing route test files for error-path coverage and add missing validation tests

## 3. E2E Test Gap-Fill

- [x] 3.1 Create `tests/e2e/test_production_history_e2e.py` — e2e test for production history page
- [x] 3.2 Create `tests/e2e/test_anomaly_overview_e2e.py` — e2e test for anomaly overview page
- [x] 3.3 Create `tests/e2e/test_admin_dashboard_e2e.py` — e2e test for admin dashboard page
- [x] 3.4 Create `tests/e2e/test_admin_performance_e2e.py` — e2e test for admin performance page
- [x] 3.5 Create `tests/e2e/test_admin_user_usage_kpi_e2e.py` — e2e test for admin user usage KPI page

## 4. Stress Test Gap-Fill

- [x] 4.1 Create `tests/stress/test_material_trace_stress.py` — stress test for material-trace endpoints
- [x] 4.2 Create `tests/stress/test_mid_section_defect_stress.py` — stress test for MSD endpoints
- [x] 4.3 Create `tests/stress/test_yield_alert_stress.py` — stress test for yield-alert endpoints
- [x] 4.4 Create `tests/stress/test_resource_history_stress.py` — stress test for resource-history endpoints
- [x] 4.5 Create `tests/stress/test_production_history_stress.py` — stress test for production-history endpoints

## 5. Frontend Test Gap-Fill

- [x] 5.1 Create `frontend/tests/resource-status.test.js` — test resource status composables and data transforms
- [x] 5.2 Create `frontend/tests/resource-history.test.js` — test resource history composables and OEE calculations
- [x] 5.3 Create `frontend/tests/production-history.test.js` — test production history data transforms
- [x] 5.4 Create `frontend/tests/admin-dashboard.test.js` — test admin dashboard utility functions
- [x] 5.5 Create `frontend/tests/admin-performance.test.js` — test admin performance metric composables
- [x] 5.6 Create `frontend/tests/admin-user-usage-kpi.test.js` — test user usage KPI composables
- [x] 5.7 Create `frontend/tests/anomaly-overview.test.js` — test anomaly overview composables
- [x] 5.8 Create `frontend/tests/mid-section-defect-composables.test.js` — test MSD composable logic
- [x] 5.9 Create `frontend/tests/material-trace-composables.test.js` — test material trace composable logic

## 6. CI Workflow Updates

- [x] 6.1 Create or extend `.github/workflows/backend-tests.yml` — run unit + integration tests on backend changes
- [x] 6.2 Create or extend `.github/workflows/frontend-tests.yml` — run frontend tests on frontend changes
- [x] 6.3 Create `.github/workflows/e2e-tests.yml` — workflow_dispatch trigger for e2e test suite
- [x] 6.4 Create `.github/workflows/stress-tests.yml` — workflow_dispatch trigger for stress test suite
- [x] 6.5 Verify all new test files are discovered by pytest / node --test runners
