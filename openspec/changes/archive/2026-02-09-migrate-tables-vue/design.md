## Context

Tables 頁面（`/tables`）是開發者工具頁面，允許瀏覽 19 張 DWH 表的欄位與內容。目前架構：
- Jinja2 模板 `index.html` extends `_base.html`，server-render `TABLES_CONFIG` 為表格卡片
- vanilla JS (237 行) 用 DOM 操作管理狀態，透過 `window.MesApi.post()` 呼叫 API
- 兩個 POST API：`/api/get_table_columns`、`/api/query_table`；一個 GET API：`/api/get_table_info`

QC-GATE 遷移已建立 Vue 3 + Vite 純前端架構模式（GET-only），本次需補齊 POST 請求模式。

## Goals / Non-Goals

**Goals:**
- 將 Tables 頁面完整遷移為 Vue 3 SFC，複用 QC-GATE 架構模式
- 建立 POST 請求在純 Vite 頁面中的標準做法（`apiPost` from `core/api.js`）
- 表格配置改由前端 `apiGet('/api/get_table_info')` 動態取得，脫離 Jinja2 context
- 遷移完成後移除 Jinja2 模板 `templates/index.html`

**Non-Goals:**
- 不修改後端 API 邏輯或 SQL 查詢（保持現有 `/api/query_table`、`/api/get_table_columns` 不變）
- 不改變 CSRF 策略（現有 CSRF 僅 enforce `/admin/*` 路徑，Tables API 不受影響）
- 不增加新功能（如分頁、排序、匯出），僅 1:1 功能遷移
- 不建立共用 Vue 元件庫（本次僅 Tables 頁面內部元件化）

## Decisions

### D1: CSRF token 不需額外處理
**選擇**：Tables 的 POST API 不需 CSRF token
**理由**：`csrf.py` 的 `should_enforce_csrf()` 僅對 `/admin/*` 路徑啟用 CSRF。`/api/query_table` 和 `/api/get_table_columns` 不在 enforce 範圍內。`apiPost()` 已內建 CSRF header 邏輯（從 `<meta>` 讀取），即使沒有 meta tag 也只是發送空字串，不會失敗。
**替代方案**：新增 CSRF token API endpoint — 不需要，因為 Tables API 本身就不 enforce。

### D2: 表格配置從 API 動態取得
**選擇**：前端在 mount 時呼叫 `GET /api/get_table_info` 取得 `TABLES_CONFIG`
**理由**：該 endpoint 已存在（`app.py:453`），直接返回 `TABLES_CONFIG` dict。無需建立新 API。
**替代方案**：將 config 打包成靜態 JSON — 不適合，config 含 row_count 等可能更新的資訊。

### D3: Vite entry 改為 HTML entry point
**選擇**：`vite.config.js` 中 tables entry 從 `src/tables/main.js` 改為 `src/tables/index.html`
**理由**：與 QC-GATE 模式一致，HTML entry 讓 Vite 處理完整的 HTML → JS → CSS pipeline。
**影響**：`npm run build` 會輸出 `tables.html`、`tables.js`、`tables.css` 到 `static/dist/`。

### D4: 元件拆分策略
**選擇**：3 個 Vue 元件 + 1 個 composable
- `App.vue` — 根佈局，管理 loading/error 狀態
- `TableCatalog.vue` — 表格卡片目錄（分類顯示）
- `DataViewer.vue` — 資料檢視器（欄位篩選 + 查詢結果表格）
- `useTableData.js` — composable 封裝 API 呼叫和狀態管理

**理由**：對應原始 UI 的兩個主要區塊（表格選擇 / 資料檢視），職責清晰。

### D5: 現有 vanilla JS main.js 直接替換
**選擇**：將現有 `frontend/src/tables/main.js` (237 行) 替換為 Vue 3 bootstrap 入口（~7 行），原始邏輯分散至 Vue 元件和 composable 中。
**理由**：vanilla JS 全部是 DOM 操作，無法漸進式遷移，需整體重寫。

## Risks / Trade-offs

- **[風險] 大表警示標記遺失**：Jinja2 模板中有 `{% if table.row_count > 10000000 %}` 顯示「大表」badge。
  → 遷移：在 `TableCatalog.vue` 中用 Vue 條件渲染實現相同邏輯。

- **[風險] Fallback inline script 移除**：`index.html` 含 ~200 行 fallback JS（Vite build 不存在時）。
  → 接受：Vite build 是 deployment 的標準流程，fallback 不再需要。

- **[風險] CSS 樣式差異**：原始 ~335 行 embedded CSS 需遷移至 `style.css`。
  → 遷移：提取核心樣式至獨立 CSS 檔案，與 QC-GATE 風格統一。
