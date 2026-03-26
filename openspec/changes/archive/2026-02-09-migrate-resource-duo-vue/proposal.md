## Why

設備即時概況（`/resource-status`，853 行 JS + 1,669 行模板）與設備歷史績效（`/resource-history`，844 行 JS + 1,531 行模板）仍為 Jinja2 + vanilla JS 架構，是最後一組使用三層階層樹表的 Jinja2 頁面。兩頁共享 E10 狀態碼集、OU%/Availability% KPI 計算、workcenter group/family/resource 三層結構、以及相同的篩選模式，適合成對遷移並抽取共用模組。

## What Changes

- 將 `/resource-status` 從 Jinja2 + vanilla JS 遷移至 Vue 3 SFC + Vite 純前端架構
- 將 `/resource-history` 從 Jinja2 + vanilla JS 遷移至 Vue 3 SFC + Vite 純前端架構
- History 頁的 4 個 ECharts 圖表改用 vue-echarts（與 QC-GATE、WIP Overview 一致）
- 抽取 `resource-shared/` 共用模組：CSS 基底、狀態常數、HierarchyTable 元件
- 兩頁 Vite entry 從 `main.js` 改為 `index.html`，Flask route 改為 `send_from_directory`
- 移除兩份 Jinja2 模板（`resource_status.html`、`resource_history.html`）
- Status 頁模板內 820 行 inline fallback script 遷移後一併移除
- 複用已建立的 `useAutoRefresh` composable（從 `wip-shared/` 移至或引用）

## Capabilities

### New Capabilities
- `resource-status-page`: 設備即時概況頁面需求 — 即時矩陣、設備卡片、LOT/JOB tooltip、狀態篩選、5 分鐘自動刷新
- `resource-history-page`: 設備歷史績效頁面需求 — 日期區間查詢、4 個 ECharts 圖表、三層階層明細表、多選篩選、CSV 匯出

### Modified Capabilities
- `vue-vite-page-architecture`: 新增 Shared CSS import 跨 resource-shared/ 的場景，與 wip-shared/ 模式一致

## Impact

- **前端**：新增 `frontend/src/resource-shared/`、修改 `frontend/src/resource-status/`、`frontend/src/resource-history/`、`frontend/vite.config.js`、`frontend/package.json`
- **後端**：`app.py` 兩條 route 改為 `send_from_directory`，API 端點不變
- **移除**：`templates/resource_status.html`、`templates/resource_history.html`
- **依賴**：無新增 npm 依賴（vue-echarts、echarts 已安裝）
