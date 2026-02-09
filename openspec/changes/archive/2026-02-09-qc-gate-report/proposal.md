## Why

目前系統缺乏 QC-GATE 站點的即時 LOT 狀態監控。QC-GATE 是製程中的品質關卡，LOT 在此站點的等待時間直接影響生產效率。需要一個視覺化報表即時呈現各 QC-GATE 站點的 LOT 分佈與等待時間，讓管理者快速識別瓶頸。

此頁面同時作為前端架構遷移的起點 — 第一個完全脫離 Jinja2 的純 Vue 3 + Vite 頁面，為後續頁面遷移建立模式。

## What Changes

- 新增 QC-GATE 即時狀態報表頁面（`/qc-gate`），使用 Vue 3 + ECharts 實作
- 新增後端 API endpoint（`/api/qc-gate/summary`），從 WIP Redis cache 篩選 QC-GATE 相關 LOT
- 前端引入 Vue 3 和 ECharts npm 套件，建立純 Vite 頁面架構模式
- 頁面以 Vite HTML entry 方式建置，完全不使用 Jinja2 template
- 頁面註冊至「報表類」drawer，狀態為 released
- 使用 `DW_MES_SPEC_WORKCENTER_V` 取得 QC-GATE 站點清單與排序
- 等待時間以 6 小時為基準分為四級：<6hr, 6-12hr, 12-24hr, >24hr
- 支援 10 分鐘自動刷新與 visibilitychange 即時刷新

## Capabilities

### New Capabilities
- `qc-gate-status-report`: QC-GATE 站點即時 LOT 狀態報表 — 包含 API 端點、Vue 3 前端頁面、圖表互動、清單篩選
- `vue-vite-page-architecture`: 純 Vue 3 + Vite 頁面架構模式 — 脫離 Jinja2 的前端建置模式、CSRF/auth 處理、與 portal iframe 整合

### Modified Capabilities
- `page-drawer-assignment`: 新增 qc-gate 頁面至報表類 drawer 的 page_status.json 配置

## Impact

- **前端**: 引入 `vue`、`echarts`、`vue-echarts` npm 依賴；修改 `vite.config.js` 加入 Vue plugin 和新 entry point
- **後端**: 新增 `qc_gate_routes.py` blueprint 和 `qc_gate_service.py` 服務；新增 Flask route serving 純靜態 HTML
- **配置**: `page_status.json` 新增 qc-gate 頁面定義
- **建置**: Vite config 需加入 `@vitejs/plugin-vue` 和 HTML entry
