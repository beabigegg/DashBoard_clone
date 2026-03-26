## Why

異常偵測後端（4 個偵測器 + 4 個 API 端點）和前端 `AnomalyBadge.vue` 已完成，但 badge 分散嵌入在 4 個獨立頁面（yield-alert-center、hold-history、reject-history、resource-history）。使用者必須逐頁切換才能得知系統是否存在異常，無法在 portal-shell 層級一眼掌握全廠異常狀態。

## What Changes

- **移除各頁面分散的 AnomalyBadge** — 從 yield-alert-center、hold-history、reject-history、resource-history 移除 `AnomalyBadge` 元件及其相關的 anomaly API 呼叫邏輯，改由 header 集中管理
- **新增 Header 異常指標元件** — 在 portal-shell header 的 HealthStatus 旁放置 `AnomalyIndicator.vue`，顯示異常總數 + 嚴重等級（ok/warning/critical），30 秒輪詢
- **新增聚合摘要 API** — `GET /api/analytics/anomaly-summary` 一次回傳 4 種偵測器的計數與嚴重度，避免 header 每次輪詢發 4 個請求
- **新增異常總覽頁面** — `/anomaly-overview` SPA 路由，展示 4 種異常的摘要卡片、演算法說明（Z-score 公式、spike 閾值等）、詳細清單表格
- **更新 portal-shell 路由基礎設施** — routeContracts、nativeModuleRegistry、navigationState、vite.config.js 註冊新頁面
- **更新合約清冊** — api_inventory.md 登錄新端點、css_inventory.md 登錄新 CSS 檔案
- **評估移除 AnomalyBadge.vue** — 若確認無其他使用者，從 `shared-ui/components/` 刪除元件

## Capabilities

### New Capabilities

- `anomaly-summary-api`: 聚合摘要端點，回傳 4 種偵測器計數 + 嚴重度分級
- `anomaly-indicator-header`: portal-shell header 異常指標元件（輪詢、狀態色、導航）
- `anomaly-overview-page`: 異常總覽頁面（摘要卡片、演算法說明、詳細表格、跳轉導航）

### Modified Capabilities

_無既有 spec 的行為變更。聚合端點建立在現有 analytics_routes 之上，不修改現有 4 個偵測端點的行為。各頁面的 AnomalyBadge 整合屬於實作層移除（非 spec 行為變更），不需要 delta spec。_

## Impact

- **後端**: `analytics_routes.py` 新增 1 個端點 + `anomaly_detection_sql_runtime.py` 新增 1 個 service 函式
- **前端（新增）**: `portal-shell/components/AnomalyIndicator.vue`、`anomaly-overview/` 頁面目錄（4 檔案）
- **前端（移除）**: 4 個頁面中的 AnomalyBadge import + 載入函式 + template 引用；若無其他使用者則刪除 `shared-ui/components/AnomalyBadge.vue`
- **Portal-shell 整合**: App.vue、style.css、routeContracts.js、navigationState.js、nativeModuleRegistry.js 各需小幅修改
- **構建**: vite.config.js 新增構建入口
- **合約清冊**: api_inventory.md + css_inventory.md 各新增 1 行
- **新增依賴**: 無
