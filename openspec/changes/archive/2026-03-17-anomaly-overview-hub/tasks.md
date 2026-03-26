## 1. 後端 — 聚合摘要端點

- [x] 1.1 在 `src/mes_dashboard/services/anomaly_detection_sql_runtime.py` 新增 `get_anomaly_summary()` 函式：內部呼叫 4 個 detect 函式，每個獨立 try/catch，回傳 `{ data: { total_count, severity, breakdown }, meta: { timestamp, latency_s, degraded } }`
- [x] 1.2 在 `src/mes_dashboard/routes/analytics_routes.py` 新增 `GET /api/analytics/anomaly-summary` 路由：apply `@_ANALYTICS_RATE_LIMIT`、檢查 feature flag、呼叫 `get_anomaly_summary()`、回傳 `success_response()`；flag 關閉時回傳 `not_found_error("功能未啟用")`
- [x] 1.3 更新 `contract/api_inventory.md`：在 `analytics_routes.py` 行的 Scope 欄位追加 `GET /api/analytics/anomaly-summary`

## 2. 前端 — 異常總覽頁面骨架

- [x] 2.1 建立 `frontend/src/anomaly-overview/index.html`（照現有頁面模式：引用 main.js）
- [x] 2.2 建立 `frontend/src/anomaly-overview/main.js`（Vue 3 createApp + mount，照 yield-alert-center 模式）
- [x] 2.3 建立 `frontend/src/anomaly-overview/App.vue`（主頁面元件，根元素加 `theme-anomaly-overview` class）
- [x] 2.4 建立 `frontend/src/anomaly-overview/style.css`（所有規則 scoped under `.theme-anomaly-overview`，顏色用 `theme()` 語義 token）

## 3. 前端 — 路由與構建註冊

- [x] 3.1 `frontend/vite.config.js`：在 `rollupOptions.input` 新增 `'anomaly-overview': resolve(__dirname, 'src/anomaly-overview/index.html')`
- [x] 3.2 `frontend/src/portal-shell/routeContracts.js`：`IN_SCOPE_REPORT_ROUTES` 加入 `'/anomaly-overview'`；`ROUTE_CONTRACTS` 新增 `/anomaly-overview` 的 `buildContract()` 條目（routeId: `anomaly-overview`, title: `異常總覽`, renderMode: `native`, scope: `in-scope`）
- [x] 3.3 `frontend/src/portal-shell/navigationState.js`：`STANDALONE_DRILLDOWN_ROUTES` 加入 `'/anomaly-overview'`
- [x] 3.4 `frontend/src/portal-shell/nativeModuleRegistry.js`：新增 `/anomaly-overview` 的 `createNativeLoader()` 條目

## 4. 前端 — Header 異常指標元件

- [x] 4.1 建立 `frontend/src/portal-shell/components/AnomalyIndicator.vue`：
  - 自包含（無 props），onMounted 啟動 30s 輪詢 `GET /api/analytics/anomaly-summary`
  - 初始狀態隱藏（`v-if` 控制），首次成功回應後才顯示
  - 404 回應 → 保持隱藏
  - 顯示：狀態色 dot（ok=綠/warning=琥珀/critical=紅+脈衝）+ 計數 badge
  - 點擊 → `router.push('/anomaly-overview')`
- [x] 4.2 在 `frontend/src/portal-shell/App.vue` 匯入 `AnomalyIndicator` 並放置在 `.shell-header-right` 內 `<HealthStatus />` 之前
- [x] 4.3 在 `frontend/src/portal-shell/style.css` 新增指標樣式（`.anomaly-indicator-wrap`、`.anomaly-trigger`、`.anomaly-count`、`.dot.critical-pulse`），顏色用 `theme()` 語義 token，脈衝動畫複用現有 `@keyframes pulse`

## 5. 前端 — 異常總覽頁面內容

- [x] 5.1 實作摘要卡片區（4 張卡片）：type label + count + severity 色指標，點擊 scroll 至對應區塊
- [x] 5.2 實作資料取得邏輯：onMount 先呼叫 summary API，再並行呼叫 4 個詳細端點，各區塊獨立 loading/error 狀態
- [x] 5.3 實作 4 個可展開詳細區塊，每區塊包含：
  - 區塊 header（type label + count badge + 展開/收合 toggle + 「前往 X →」導航連結）
  - 演算法說明卡片（靜態中文文字：公式 + window + threshold）
  - 資料表格（yield: 日期/產線/封裝/良率%/Z-score/方向；reject: 日期/群組/目前率/基線率/變化%；hold: 日期/Lot/原因/工作站/時數/門檻；equipment: 日期/設備/目前OU%/基線OU%/偏差）
- [x] 5.4 實作行點擊導航（yield→`/yield-alert-center`、reject→`/reject-history`、hold→`/hold-history`、equipment→`/resource-history`）
- [x] 5.5 實作預設展開邏輯：count > 0 的區塊展開，count = 0 的收合

## 6. 移除各頁面分散的 AnomalyBadge

- [x] 6.1 `frontend/src/yield-alert-center/App.vue`：移除 AnomalyBadge import、`anomalyCount`/`anomalyItems`/`anomalyLoading` ref、`loadYieldAnomalies()` 函式、onMounted 中的呼叫、template 中的 `<AnomalyBadge>` 標籤
- [x] 6.2 `frontend/src/hold-history/App.vue`：移除 AnomalyBadge import、相關 ref、`loadHoldOutliers()` 函式、onMounted 呼叫、template 中的 `<AnomalyBadge>`
- [x] 6.3 `frontend/src/reject-history/App.vue`：移除 AnomalyBadge import、相關 ref、`loadRejectSpikes()` 函式、onMounted 呼叫、template 中的 `<AnomalyBadge>`
- [x] 6.4 `frontend/src/resource-history/App.vue`：移除 AnomalyBadge import、相關 ref、`loadEquipmentDeviations()` 函式、onMounted 呼叫、template 中的 `<AnomalyBadge>`
- [x] 6.5 刪除 `frontend/src/shared-ui/components/AnomalyBadge.vue`

## 7. 合約清冊更新

- [x] 7.1 更新 `contract/css_inventory.md`：在 Route-Local Feature Layers 表格新增 `frontend/src/anomaly-overview/style.css | theme-anomaly-overview | anomaly-overview`

## 8. 驗證

- [ ] 8.1 手動驗證：`GET /api/analytics/anomaly-summary` 回傳正確聚合計數；feature flag 關閉時回傳 404
- [ ] 8.2 手動驗證：Header 指標在有異常時顯示計數 + 狀態色；無異常/flag 關閉時隱藏
- [ ] 8.3 手動驗證：點擊指標導航至 `/anomaly-overview`；總覽頁 4 區塊各自載入；行點擊導航至對應頁面
- [ ] 8.4 手動驗證：4 個原頁面（yield-alert-center、hold-history、reject-history、resource-history）不再顯示 AnomalyBadge，無殘留的 anomaly API 呼叫
- [ ] 8.5 確認 `frontend/src/shared-ui/components/AnomalyBadge.vue` 已刪除
- [ ] 8.6 執行 `pytest tests/ -v` 確保既有測試通過
- [ ] 8.7 執行 Vite build 確保無構建錯誤
