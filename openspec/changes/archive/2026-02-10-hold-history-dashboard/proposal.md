## Why

Hold Overview 和 Hold Detail 都是基於 DW_MES_LOT_V 的即時快照，只能回答「現在線上有什麼 Hold」。主管需要追蹤歷史趨勢來回答「Hold 狀況是在改善還是惡化？哪些原因最耗時？哪個部門處理最慢？」。目前這些分析只能透過 BI 工具 (PJMES043) 手動查詢，無法即時在 Dashboard 上呈現。

## What Changes

- 新增 `/hold-history` 頁面，提供 Hold/Release 歷史績效 Dashboard
- 新增 5 支 API endpoints (`/api/hold-history/trend`, `reason-pareto`, `duration`, `department`, `list`)
- 新增 `hold_history_service.py` 服務層，查詢 `DWH.DW_MES_HOLDRELEASEHISTORY` 表
- 新增 SQL 檔案集中管理在 `src/mes_dashboard/sql/hold_history/` 目錄
- trend API 採用 Redis 快取策略（近二月聚合資料，12hr TTL）
- 翻譯 `docs/hold_history.md` 中的 calendar-spine cross-join 商業邏輯為參數化 SQL
- 新增 Vite entry point `src/hold-history/index.html`
- 新增頁面註冊至 `data/page_status.json`

## Capabilities

### New Capabilities
- `hold-history-page`: Hold 歷史績效 Dashboard 前端頁面，包含篩選器、Summary KPIs、Daily Trend 圖、Reason Pareto、Duration 分布、負責人統計、明細表，及 Reason Pareto 的 cascade filter 機制
- `hold-history-api`: Hold 歷史績效 API 後端，包含 5 支 endpoints、Oracle 查詢（含 calendar-spine 商業邏輯）、Redis 快取策略、SQL 集中管理

### Modified Capabilities
- `vue-vite-page-architecture`: 新增 Hold History entry point 至 Vite 配置

## Impact

- **後端**: 新增 Flask Blueprint `hold_history_routes.py`、服務層 `hold_history_service.py`、SQL 檔案 `sql/hold_history/`
- **前端**: 新增 `frontend/src/hold-history/` 頁面目錄，使用 ECharts (BarChart, LineChart) 及 wip-shared composables
- **資料庫**: 直接查詢 `DWH.DW_MES_HOLDRELEASEHISTORY`（~310K rows），無 schema 變更
- **Redis**: 新增 `hold_history:daily:{YYYY-MM}` 快取 key
- **配置**: `vite.config.js` 新增 entry、`page_status.json` 新增頁面註冊
- **既有功能**: 無影響，完全獨立的新頁面和新 API
