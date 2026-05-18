# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- frontend build config (vite.config.ts)
- frontend portal-shell routing/navigation
- frontend feature apps: tables, admin-performance, admin-user-usage-kpi
- Flask routes (admin_routes.py, dashboard_routes.py, analytics_routes.py)
- contracts: api-inventory, css-inventory, optionally business-rules and ci-gate-contract
- backend + frontend tests (legacy + e2e suites)

## Allowed Paths
- specs/changes/remove-unused-pages/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/vite.config.ts
- frontend/src/tables/
- frontend/src/admin-performance/
- frontend/src/admin-user-usage-kpi/
- frontend/src/portal-shell/
- frontend/tests/legacy/
- frontend/tests/playwright/
- src/mes_dashboard/routes/admin_routes.py
- src/mes_dashboard/routes/dashboard_routes.py
- src/mes_dashboard/routes/analytics_routes.py
- src/mes_dashboard/app.py
- src/mes_dashboard/services/page_registry.py
- src/mes_dashboard/services/navigation_contract.py
- src/mes_dashboard/templates/admin/
- tests/e2e/test_admin_performance_e2e.py
- tests/e2e/test_admin_user_usage_kpi_e2e.py
- tests/e2e/test_tables_e2e.py
- tests/test_admin_routes.py
- tests/test_dashboard_routes.py
- tests/test_app_factory.py
- frontend/tests/legacy/loading-standardization.test.js
- tests/test_template_integration.py
- tests/test_performance_integration.py
- tests/test_portal_shell_routes.py
- tests/test_page_registry.py
- tests/test_auth_integration.py
- tests/e2e/test_admin_auth_e2e.py
- tests/e2e/test_global_connection.py
- tests/stress/test_frontend_stress.py
- contracts/api/api-inventory.md
- contracts/api/api-contract.md
- contracts/css/css-inventory.md
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md

## Required Contracts
- contracts/api/api-inventory.md
- contracts/css/css-inventory.md
- contracts/business/business-rules.md (review only; modify only if page registry rules reference removed pages)
- contracts/ci/ci-gate-contract.md (review only; modify if frontend-build gate inventory changes)
- contracts/CHANGELOG.md

## Required Tests
- frontend/tests/legacy/ (audit + delete admin-performance, admin-user-usage-kpi, tables tests)
- frontend/tests/playwright/ (audit + delete any tables specs)
- tests/e2e/test_admin_performance_e2e.py (delete)
- tests/e2e/test_admin_user_usage_kpi_e2e.py (delete)
- tests/e2e/test_tables_e2e.py (delete)
- tests/test_admin_routes.py (audit for assertions against removed redirects)
- tests/test_dashboard_routes.py (audit for tables references)
- tests/test_app_factory.py (audit for blueprint registration assertions)
- frontend/tests/legacy/loading-standardization.test.js (lines 222, 234 reference tables DataViewer)
- tests/test_template_integration.py (lines 83-88, 287-296, 343, 358 reference /tables)
- tests/test_performance_integration.py (lines 53, 375-404 reference /admin/performance and /admin/user-usage-kpi)
- tests/test_portal_shell_routes.py (line 462 references /tables redirect mapping)
- tests/test_page_registry.py (lines 24, 64-65, 178 reference /tables fixture)
- tests/test_auth_integration.py (lines 248-264 reference /tables)
- tests/e2e/test_admin_auth_e2e.py (lines 33, 162, 185, 237-261, 279, 304 reference /tables)
- tests/e2e/test_global_connection.py (lines 129-130 contain test_tables_page_loads)
- tests/stress/test_frontend_stress.py (9 lines reference /tables — must substitute with kept route)

## Agent Work Packets

### change-classifier
- specs/changes/remove-unused-pages/
- specs/context/project-map.md
- specs/context/contracts-index.md

### contract-reviewer
- specs/changes/remove-unused-pages/
- contracts/api/api-inventory.md
- contracts/api/api-contract.md
- contracts/css/css-inventory.md
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md

### test-strategist
- specs/changes/remove-unused-pages/
- frontend/tests/legacy/
- frontend/tests/playwright/
- tests/e2e/test_admin_performance_e2e.py
- tests/e2e/test_admin_user_usage_kpi_e2e.py
- tests/e2e/test_tables_e2e.py
- tests/test_admin_routes.py
- tests/test_dashboard_routes.py
- tests/test_app_factory.py

### ci-cd-gatekeeper
- specs/changes/remove-unused-pages/
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md

### implementation-planner
- specs/changes/remove-unused-pages/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/vite.config.ts
- frontend/src/tables/
- frontend/src/admin-performance/
- frontend/src/admin-user-usage-kpi/
- frontend/src/portal-shell/
- src/mes_dashboard/routes/admin_routes.py
- src/mes_dashboard/routes/dashboard_routes.py
- src/mes_dashboard/routes/analytics_routes.py
- src/mes_dashboard/app.py
- src/mes_dashboard/services/page_registry.py
- contracts/api/api-inventory.md
- contracts/css/css-inventory.md

### backend-engineer
- specs/changes/remove-unused-pages/
- src/mes_dashboard/routes/admin_routes.py
- src/mes_dashboard/routes/dashboard_routes.py
- src/mes_dashboard/routes/analytics_routes.py
- src/mes_dashboard/app.py
- src/mes_dashboard/services/page_registry.py
- src/mes_dashboard/services/navigation_contract.py
- src/mes_dashboard/templates/admin/
- tests/test_admin_routes.py
- tests/test_dashboard_routes.py
- tests/test_app_factory.py
- contracts/api/api-inventory.md
- contracts/CHANGELOG.md

### frontend-engineer
- specs/changes/remove-unused-pages/
- frontend/vite.config.ts
- frontend/src/tables/
- frontend/src/admin-performance/
- frontend/src/admin-user-usage-kpi/
- frontend/src/portal-shell/
- frontend/tests/legacy/
- frontend/tests/playwright/
- contracts/css/css-inventory.md
- contracts/CHANGELOG.md

### qa-reviewer
- specs/changes/remove-unused-pages/
- contracts/ci/ci-gate-contract.md

## Context Expansion Requests
- Agents should file CERs if the Flask `tables` route turns out to live outside the allowed route files, or if the portal-shell route registration is split across more files than those listed above.

## Approved Expansions
- `frontend/package.json`: build script contains a stale `cp dist/src/tables/index.html` command that will fail on CI clean build after tables removal. Approved for editing to remove the stale cp entry.
