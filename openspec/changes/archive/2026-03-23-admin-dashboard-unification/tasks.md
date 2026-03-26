## Phase 1: 共用元件層建立

- [x] 1.1 建立 `frontend/src/admin-shared/components/` 目錄
- [x] 1.2 將 `admin-performance/components/StatusDot.vue` 移至 `admin-shared/components/StatusDot.vue`
  - 原位保留 re-export：`export { default } from '../../admin-shared/components/StatusDot.vue'`
- [x] 1.3 將 `admin-performance/components/StatCard.vue` 移至 `admin-shared/components/StatCard.vue`
  - 原位保留 re-export
- [x] 1.4 將 `admin-performance/components/GaugeBar.vue` 移至 `admin-shared/components/GaugeBar.vue`
  - 原位保留 re-export
- [x] 1.5 將 `admin-performance/components/TrendChart.vue` 移至 `admin-shared/components/TrendChart.vue`
  - 原位保留 re-export
- [x] 1.6 建立 `frontend/src/admin-shared/composables/useAdminData.js`
  - `useSystemStatus()` — 封裝 `/admin/api/system-status` 呼叫
  - `useMetrics()` — 封裝 `/admin/api/metrics` 呼叫
  - `usePerfDetail()` — 封裝 `/admin/api/performance-detail` 呼叫
  - `usePerfHistory(minutes, bucket)` — 封裝 `/admin/api/performance-history` 呼叫
  - `useStorageInfo()` — 封裝 `/admin/api/storage-info` 呼叫
  - `useUsageKpi(startDate, endDate, department)` — 封裝 `/admin/api/user-usage-kpi` 呼叫
  - `useLogs(level, q, limit, offset)` — 封裝 `/admin/api/logs` 呼叫
  - `useHealthSummary()` — 封裝 `/health` 呼叫（for 總覽 Tab）
  - 每個都回傳 `{ data, loading, error, refresh }` reactive 物件
- [x] 1.7 驗證舊 `admin-performance` SPA 仍正常運作（re-export 不破壞）

## Phase 2: 新 SPA 骨架

- [x] 2.1 建立 `frontend/src/admin-dashboard/index.html`
  - 依照其他 SPA 模式（tailwind.css + 自有 style.css + main.js）
- [x] 2.2 建立 `frontend/src/admin-dashboard/main.js`
  - Vue createApp + mount
- [x] 2.3 建立 `frontend/src/admin-dashboard/App.vue`
  - Tab bar：`['總覽', '效能', '快取', 'Worker', '用戶', '日誌']`
  - `<KeepAlive>` + `<component :is="...">` 動態切換
  - 自動更新 toggle（useAutoRefresh, 30s）
  - Tab 切換時立即 refresh
  - Header gradient 統一風格
- [x] 2.4 建立 `frontend/src/admin-dashboard/style.css`
  - 合併 admin-performance/style.css 和 admin-user-usage-kpi/style.css 的共用規則
  - 移除重複定義，統一使用 `.theme-admin-dashboard` scope
  - Tab bar 樣式
- [x] 2.5 修改 `frontend/vite.config.js`
  - 新增 `'admin-dashboard': resolve(__dirname, 'src/admin-dashboard/index.html')` 入口
- [x] 2.6 修改 `src/mes_dashboard/routes/admin_routes.py`
  - 新增 `@admin_bp.route("/dashboard")` 路由，serve `admin-dashboard.html`
- [x] 2.7 驗證新 SPA 可 build 並載入（空 Tab 狀態）

## Phase 3: Tab 內容遷移

### 3A: 總覽 Tab（新建）

- [x] 3.1 建立 `frontend/src/admin-dashboard/tabs/OverviewTab.vue`
  - 4 個 StatusDot 卡片（Database / Redis / Circuit Breaker / System Memory）
  - Dead worker alert banner（條件式顯示：`rq_queue_depth > 0 && rq_workers_total === 0`）
  - 4 個 mini TrendChart（延遲 P95 / 連線池飽和度 / Worker 記憶體 / Cache 命中率）
  - Active alerts/warnings 列表
  - expose `refresh()` method
- [x] 3.2 使用 `useHealthSummary()` + `usePerfHistory()` 取資料

### 3B: 效能 Tab（從 performance 拆出）

- [x] 3.3 建立 `frontend/src/admin-dashboard/tabs/PerformanceTab.vue`
  - 查詢效能 section（P50/P95/P99 + slow count/rate + latency bar chart）
  - 查詢延遲趨勢 TrendChart
  - 連線池 section（GaugeBar 飽和度 + pool stats）
  - 連線池趨勢 TrendChart
  - expose `refresh()` method
- [x] 3.4 使用 `useMetrics()` + `usePerfDetail()` + `usePerfHistory()` 取資料

### 3C: 快取 Tab（從 performance 拆出）

- [x] 3.5 建立 `frontend/src/admin-dashboard/tabs/CacheTab.vue`
  - Redis 快取 section（記憶體 GaugeBar + stats + namespace table）
  - Redis 記憶體趨勢 TrendChart
  - 記憶體快取 section（ProcessLevelCache cards）
  - Route Cache section（mode/hit rate/miss rate）
  - 快取命中率趨勢 TrendChart
  - Pareto 物化層 section（stats + fallback reasons table）
  - expose `refresh()` method
- [x] 3.6 使用 `usePerfDetail()` + `usePerfHistory()` 取資料

### 3D: Worker Tab（從 performance 拆出）

- [x] 3.7 建立 `frontend/src/admin-dashboard/tabs/WorkerTab.vue`
  - RQ Worker section（availability + busy/total + queue depth + failed）
  - Heavy Query slots GaugeBar
  - Worker 狀態 table + Queue 狀態 table
  - Worker/Queue 趨勢 TrendChart ×2
  - Worker 記憶體守衛 section（RSS GaugeBar + stats）
  - Worker 記憶體趨勢 TrendChart
  - Worker 控制 section（重啟按鈕 + restart modal）
  - 儲存空間管理 section（SQLite + Logs + Archive tables + cleanup buttons）
  - expose `refresh()` method
- [x] 3.8 使用 `usePerfDetail()` + `usePerfHistory()` + `useStorageInfo()` 取資料

### 3E: 用戶 Tab（從 usage-kpi 遷入）

- [x] 3.9 建立 `frontend/src/admin-dashboard/tabs/UsageTab.vue`
  - 日期篩選 + 部門篩選（保留現有 filter bar）
  - Overview KpiCards（unique users / total sessions / avg duration / active）
  - DAU 趨勢圖
  - 登入時段分佈 + 使用時長分佈（grid 2-col）
  - Top 使用者 table + 部門統計 table（grid 2-col）
  - 近期登入記錄 table
  - expose `refresh()` method
- [x] 3.10 使用 `useUsageKpi()` 取資料
  - 直接 import 現有 `admin-user-usage-kpi/components/` 的 7 個元件

### 3F: 日誌 Tab（從 performance 拆出）

- [x] 3.11 建立 `frontend/src/admin-dashboard/tabs/LogsTab.vue`
  - 等級篩選 + 搜尋 + 清理按鈕
  - 日誌 table（時間/等級/訊息）+ level-based row coloring
  - 分頁控制
  - expose `refresh()` method
- [x] 3.12 使用 `useLogs()` 取資料

## Phase 4: 收尾與整合

- [x] 4.1 更新 `contract/api_inventory.md`
  - 新增 `/admin/dashboard` 頁面路由描述
- [x] 4.2 更新 `contract/css_inventory.md`（如新增 CSS 檔案）
- [x] 4.3 驗證 `npm run build` 成功
- [ ] 4.4 驗證新面板所有 6 個 Tab 正常載入與資料展示
- [x] 4.5 驗證舊面板 `/admin/performance` 和 `/admin/user-usage-kpi` 仍可用
