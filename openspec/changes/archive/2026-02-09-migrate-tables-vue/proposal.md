## Why

Tables 頁面（`/tables`）是完全獨立的開發工具頁面，無跨頁面 drill-down 依賴，且行數最少（237 行 JS），是建立 POST/CSRF 請求模式的理想候選。QC-GATE 遷移已建立 GET-only 的 Vue 3 + Vite 架構模式，現在需要補齊 POST 請求模式，為後續更複雜頁面遷移鋪路。

## What Changes

- 將 `/tables` 頁面從 Jinja2 模板 + vanilla JS 遷移為純 Vue 3 + Vite SFC 架構
- Flask route 從 `render_template()` 改為 `send_from_directory()`，不再傳入 `TABLES_CONFIG` context
- 前端改用 `/api/get_table_info` (GET) 取得表格配置，取代 Jinja2 server-render
- API 呼叫從 `window.MesApi.post()` 改為 `apiPost()` from `core/api.js`
- 純 Vite 頁面發出 POST 請求時需自行攜帶 CSRF token（透過 `<meta>` tag 或從 API 取得）
- Vite config entry 從 JS-only (`tables/main.js`) 改為 HTML entry (`tables/index.html`)
- 保留現有 Jinja2 模板作為 fallback 直到驗證完成後移除

## Capabilities

### New Capabilities
- `tables-query-page`: 數據表查詢頁面的功能需求（表格選擇、動態欄位篩選、查詢結果顯示）

### Modified Capabilities
- `vue-vite-page-architecture`: 新增 POST 請求 + CSRF token 處理模式（現有 spec 僅涵蓋 GET）

## Impact

- **前端**：`frontend/src/tables/` 整個目錄重寫（main.js → Vue 3 SFC 結構）
- **後端**：`app.py` 中 `/tables` route 改為 `send_from_directory`
- **Vite config**：tables entry 改為 HTML entry point
- **CSRF**：純 Vite 頁面無 Jinja2 `{{ csrf_token() }}`，需建立替代方案（API endpoint 或 cookie-based）
- **模板**：`templates/index.html` 遷移完成後可移除
- **API**：現有 `/api/get_table_info`、`/api/get_table_columns`、`/api/query_table` 不變
