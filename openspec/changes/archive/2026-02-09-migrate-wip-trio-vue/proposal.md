## Why

WIP 三頁（Overview、Detail、Hold Detail）是目前使用量最高的報表頁面，仍依賴 Jinja2 模板 + vanilla JS 架構。三頁有 drill-down 導覽依賴關係，必須作為一個整體遷移至 Vue 3 + Vite 純前端架構，以統一前端技術棧並消除 `_base.html` / `window.MesApi` 依賴。QC-GATE 和 Tables 頁面已成功建立遷移模式，現在是批量套用此模式的時機。

## What Changes

- 將 `/wip-overview`（784 行 vanilla JS）重寫為 Vue 3 SFC 元件，包含 ECharts Pareto 圖、autocomplete 篩選、狀態卡片矩陣互動
- 將 `/wip-detail`（821 行 vanilla JS）重寫為 Vue 3 SFC 元件，包含 4 sticky 欄位表格、動態 spec 欄、inline lot detail panel
- 將 `/hold-detail`（336 行 vanilla JS）重寫為 Vue 3 SFC 元件，包含 age/workcenter/package 三維篩選
- 三頁 Vite entry 從 `main.js` 改為 `index.html`，Flask route 從 `render_template` 改為 `send_from_directory`
- 刪除三個 Jinja2 模板（`wip_overview.html`、`wip_detail.html`、`hold_detail.html`）
- Hold Detail 移除 Jinja2 server-side 注入（`reason`、`hold_type`），改為前端 URL params + 常數判斷
- Hold Detail 新增 10 分鐘自動刷新 + AbortController（與 Overview/Detail 一致）
- 提取三頁共用 CSS 變數與基礎樣式為共用模組
- 所有 `window.MesApi.get()` 呼叫改為 `apiGet()` from `core/api.js`

## Capabilities

### New Capabilities
- `wip-overview-page`: WIP Overview 頁面的功能需求（summary、matrix、hold pareto、autocomplete 篩選、狀態卡片互動、drill-down 導覽）
- `wip-detail-page`: WIP Detail 頁面的功能需求（workcenter lot 明細、sticky 欄位表格、spec 動態欄、inline lot detail panel、autocomplete 篩選、狀態卡片互動）
- `hold-detail-page`: Hold Detail 頁面的功能需求（hold reason 分析、age/workcenter/package 三維篩選、分頁 lot 明細）

### Modified Capabilities
- `vue-vite-page-architecture`: 新增三頁的 Vite entry 與 chunk splitting 規則，擴展 ECharts 共用 chunk 至 Overview 頁面

## Impact

- **前端**：`frontend/src/wip-overview/`、`frontend/src/wip-detail/`、`frontend/src/hold-detail/` 目錄結構重組為 Vue 3 SFC
- **Vite 配置**：`vite.config.js` 三個 entry 從 `main.js` 改為 `index.html`
- **Flask 路由**：`app.py` 中 `/wip-overview`、`/wip-detail` 改為 `send_from_directory`；`hold_routes.py` 中 `/hold-detail` 改為 `send_from_directory`（需保留 reason 驗證邏輯改為 API 層）
- **模板刪除**：`templates/wip_overview.html`、`templates/wip_detail.html`、`templates/hold_detail.html`
- **共用模組**：`core/wip-derive.js`、`core/autocomplete.js` 保持不變（已為 ES module）；`core/table-tree.js` 的 `escapeHtml` 在 Vue 中不再需要
- **建置腳本**：`package.json` build script 需 copy 三個新 HTML 檔案
- **後端 API**：所有 API endpoint 不變，僅 `/hold-detail` 頁面路由變更
