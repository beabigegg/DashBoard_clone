## 1. Vue 3 前端結構建立

- [x] 1.1 建立 `frontend/src/tables/index.html` — 純 Vite HTML entry point（參照 qc-gate 模式）
- [x] 1.2 重寫 `frontend/src/tables/main.js` — Vue 3 createApp bootstrap（取代原 237 行 vanilla JS）
- [x] 1.3 建立 `frontend/src/tables/style.css` — 從 Jinja2 模板提取核心樣式

## 2. Vue 元件開發

- [x] 2.1 建立 `frontend/src/tables/App.vue` — 根元件，管理 loading/error 全局狀態與佈局
- [x] 2.2 建立 `frontend/src/tables/components/TableCatalog.vue` — 表格卡片目錄（分類顯示、大表 badge、active 狀態）
- [x] 2.3 建立 `frontend/src/tables/components/DataViewer.vue` — 資料檢視器（欄位篩選輸入、查詢結果表、filter tag、close）

## 3. Composable 與 API 整合

- [x] 3.1 建立 `frontend/src/tables/composables/useTableData.js` — 封裝 apiGet/apiPost 呼叫、table config/columns/query 狀態管理

## 4. Vite 與 Flask 路由整合

- [x] 4.1 更新 `frontend/vite.config.js` — tables entry 從 `main.js` 改為 `index.html`
- [x] 4.2 更新 `src/mes_dashboard/app.py` — `/tables` route 改為 `send_from_directory`

## 5. 清理與驗證

- [x] 5.1 移除 Jinja2 模板 `src/mes_dashboard/templates/index.html`
- [x] 5.2 移除 `app.py` 中 `/tables` route 的 `TABLES_CONFIG` import（如不再被其他地方使用）
- [x] 5.3 執行 `npm run build` 驗證建置成功，確認 `static/dist/tables.html` 產出
