# Change Proposal: Remove Excel Query Feature

## Summary

Excel Query 是前站使用的批次查詢工具，已不再需要。整個前後端完整移除，消除 2 處 direct connection 使用，減少維護負擔。

## Motivation

- Excel Query 僅供前站使用，上線後不需要
- 該功能使用 `get_db_connection()` 直接建立非池化連線（2 處），繞過連線池管理
- 移除後減少 33 個檔案的維護成本
- 簡化 CI/CD pipeline 和前端 build

## Scope

### 刪除的檔案 (13 個 + 1 目錄)

**Backend:**
- `src/mes_dashboard/routes/excel_query_routes.py`
- `src/mes_dashboard/services/excel_query_service.py`
- `src/mes_dashboard/templates/excel_query.html`

**Frontend:**
- `frontend/src/excel-query/` (整個目錄: App.vue, main.js, style.css, composables/)

**Tests:**
- `tests/test_excel_query_service.py`
- `tests/test_excel_query_routes.py`
- `tests/test_excel_query_e2e.py`

**Build Output:**
- `src/mes_dashboard/static/dist/excel-query.js`
- `src/mes_dashboard/static/dist/excel-query.js.map`

### 需編輯的檔案 (20 個)

**Route Registration:**
- `src/mes_dashboard/routes/__init__.py` — 移除 excel_query_bp import 和 register

**Frontend Config:**
- `frontend/vite.config.js` — 移除 excel-query entry point
- `frontend/src/portal-shell/nativeModuleRegistry.js` — 移除 /excel-query 路由
- `frontend/src/portal-shell/routeContracts.js` — 移除 /excel-query contract

**Registry/Config:**
- `src/mes_dashboard/services/page_registry.py` — 移除 LEGACY_NAV_ASSIGNMENTS 項目
- `data/page_status.json` — 移除 /excel-query 頁面定義

**Contracts:**
- `contract/api_inventory.md` — 移除 excel_query_routes.py 條目
- `contract/css_inventory.md` — 移除 excel-query/style.css 條目
- `shared/field_contracts.json` — 移除 excel_query 物件

**Tests (移除引用):**
- `tests/test_portal_shell_routes.py`
- `tests/test_app_factory.py`
- `tests/test_asset_readiness_policy.py`
- `tests/test_api_contract.py`
- `tests/test_field_contracts.py`
- `tests/test_template_integration.py`
- `frontend/tests/portal-shell-parity-table-chart-matrix.test.js`
- `frontend/tests/portal-shell-route-contract-governance.test.js`
- `frontend/tests/portal-shell-route-query.test.js`
- `frontend/tests/portal-shell-wave-a-smoke.test.js`
- `frontend/tests/portal-shell-wave-b-native-smoke.test.js`

## Risk

- **低風險** — 純移除，無功能依賴
- 移除後跑 `pytest tests/ -v` 確認全部通過
- 前端 `npm run build` 確認無斷裂引用

## Acceptance Criteria

- [ ] 所有列出的檔案已刪除/編輯
- [ ] `pytest tests/ -v` 全部通過 (扣除 integration/e2e markers)
- [ ] `npm run build` 成功
- [ ] `/excel-query` URL 回 404
