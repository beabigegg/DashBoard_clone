## 1. Delete Excel Query files

- [x] 1.1 Delete backend files: `routes/excel_query_routes.py`, `services/excel_query_service.py`, `templates/excel_query.html`
- [x] 1.2 Delete frontend directory: `frontend/src/excel-query/` (App.vue, main.js, style.css, composables/)
- [x] 1.3 Delete test files: `tests/test_excel_query_service.py`, `tests/test_excel_query_routes.py`, `tests/test_excel_query_e2e.py`
- [x] 1.4 Delete build output: `static/dist/excel-query.js`, `static/dist/excel-query.js.map`

## 2. Remove backend references

- [x] 2.1 Edit `routes/__init__.py` — remove excel_query_bp import and register call
- [x] 2.2 Edit `services/page_registry.py` — remove LEGACY_NAV_ASSIGNMENTS excel-query item

## 3. Remove frontend config references

- [x] 3.1 Edit `frontend/vite.config.js` — remove excel-query entry point
- [x] 3.2 Edit `frontend/src/portal-shell/nativeModuleRegistry.js` — remove /excel-query route
- [x] 3.3 Edit `frontend/src/portal-shell/routeContracts.js` — remove /excel-query contract

## 4. Update registry and data files

- [x] 4.1 Edit `data/page_status.json` — remove /excel-query page definition
- [x] 4.2 Edit `shared/field_contracts.json` — remove excel_query object

## 5. Update contract documents

- [x] 5.1 Edit `contract/api_inventory.md` — remove excel_query_routes.py entries
- [x] 5.2 Edit `contract/css_inventory.md` — remove excel-query/style.css entry

## 6. Clean up test references

- [x] 6.1 Edit `tests/test_portal_shell_routes.py` — remove excel-query references
- [x] 6.2 Edit `tests/test_app_factory.py` — remove excel-query references
- [x] 6.3 Edit `tests/test_asset_readiness_policy.py` — remove excel-query references
- [x] 6.4 Edit `tests/test_api_contract.py` — remove excel-query references
- [x] 6.5 Edit `tests/test_field_contracts.py` — remove excel-query references
- [x] 6.6 Edit `tests/test_template_integration.py` — remove excel-query references
- [x] 6.7 Edit `frontend/tests/portal-shell-parity-table-chart-matrix.test.js` — remove excel-query references
- [x] 6.8 Edit `frontend/tests/portal-shell-route-contract-governance.test.js` — remove excel-query references
- [x] 6.9 Edit `frontend/tests/portal-shell-route-query.test.js` — remove excel-query references
- [x] 6.10 Edit `frontend/tests/portal-shell-wave-a-smoke.test.js` — remove excel-query references
- [x] 6.11 Edit `frontend/tests/portal-shell-wave-b-native-smoke.test.js` — remove excel-query references

## 7. Verification

- [x] 7.1 Run `grep -r "excel.query\|excel_query\|excelQuery" --include="*.py" --include="*.js" --include="*.vue" --include="*.json" --include="*.md"` and confirm no residual references outside openspec/
- [x] 7.2 Run `pytest tests/ -v` and confirm all tests pass
- [x] 7.3 Run `cd frontend && npm run build` and confirm build succeeds with no excel-query output
