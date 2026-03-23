## Context

兩個獨立 admin SPA（`admin-performance`、`admin-user-usage-kpi`）合併為單一 Tab-based dashboard。現有 4 個共用元件（StatusDot、StatCard、GaugeBar、TrendChart）需提升為 shared-ui 層級。後端 API 不變。

現有基礎設施：
- `frontend/src/admin-performance/` — 效能監控 SPA（App.vue ~520 行、4 components、style.css）
- `frontend/src/admin-user-usage-kpi/` — 使用者 KPI SPA（App.vue ~140 行、7 components、style.css）
- `frontend/src/shared-ui/components/` — 全域共用元件（EmptyState、MultiSelect 等）
- `frontend/src/shared-composables/` — 共用 composables（useAutoRefresh、useAsyncJobPolling 等）
- `frontend/src/core/api.js` — 共用 API 工具
- 後端 `/admin/performance` 和 `/admin/user-usage-kpi` 各自 serve 獨立 HTML

## Goals / Non-Goals

**Goals:**
- 合併為單一 admin SPA，Tab-based navigation
- 新增「總覽」Tab 整合系統健康一覽
- 共用元件提升至 shared-ui
- 統一 auto-refresh、loading、error 處理模式
- portal-shell sidebar 增加 admin dashboard 連結

**Non-Goals:**
- 後端 API 重構
- 新增即時推送（WebSocket）
- 新增 endpoint-level 延遲分析（後端目前不提供 per-endpoint 資料）

## Decisions

### Decision 1: 單一 SPA + Tab component 切換（而非 Vue Router）

**選擇：Tab component 動態切換（`<component :is="...">`）**

理由：
- 6 個 Tab 都在同一個 admin 頁面內，不需要 URL routing
- 現有 admin SPAs 都不用 Vue Router
- 動態切換 + `<KeepAlive>` 可以保留 Tab 狀態（如日誌篩選條件、趨勢圖時間範圍）
- 簡化建構，不需引入 vue-router 依賴

替代方案（放棄）：
- Vue Router：過度工程，admin 頁面不需要深層路由
- 獨立頁面 + iframe：破碎體驗，已在問題中否定

### Decision 2: 共用元件提升至 admin-shared/（而非 shared-ui/）

**選擇：`frontend/src/admin-shared/components/`**

理由：
- StatusDot、StatCard、GaugeBar、TrendChart 是 admin 專用元件（依賴 echarts、admin 色調）
- 放入 `shared-ui/` 會汙染全域命名空間（shared-ui 用於業務頁面）
- `admin-shared/` 作為 admin 模組的共用層，邏輯清楚
- 業務頁面不應依賴 admin 元件

### Decision 3: 統一自動更新 — 全域 30s polling + per-tab 控制

**選擇：App 層 `useAutoRefresh`，每個 Tab expose `refresh()` method**

理由：
- 已有 `useAutoRefresh` composable 可直接使用
- App 層控制 30s interval，每次呼叫當前 active tab 的 `refresh()`
- Tab 切換時立即 refresh 新 tab（`watch(activeTab, ...)`）
- 非 active tabs 因 KeepAlive 保持上次資料，不浪費頻寬

### Decision 4: 舊 SPA 保留但標記 deprecated

**選擇：保留舊檔案，新 SPA 作為預設入口**

理由：
- 避免一次性 breaking change — 如果新面板有問題可快速回退
- `/admin/performance` 和 `/admin/user-usage-kpi` 路由仍可用
- `/admin/dashboard` 為新面板入口
- 下一個 change 再移除舊 SPA（確認穩定後）

### Decision 5: 「總覽」Tab 數據來源

**選擇：複用 `/health` + `/api/performance-history` 兩個 API**

理由：
- `/health` 已包含 DB/Redis/CB/pool/memory/RQ 全部狀態
- `/api/performance-history` 已提供 30s 時序資料（latency/pool/memory/cache）
- 不需新 API，只需前端聚合展示
- dead worker alert 從 `/health` 的 `async_workers` + `warnings` 取得

## Architecture

### 檔案結構

```
frontend/src/
├── admin-shared/                    ← NEW: admin 共用元件層
│   ├── components/
│   │   ├── StatusDot.vue            ← 從 admin-performance 移入
│   │   ├── StatCard.vue             ← 從 admin-performance 移入
│   │   ├── GaugeBar.vue             ← 從 admin-performance 移入
│   │   └── TrendChart.vue           ← 從 admin-performance 移入
│   └── composables/
│       └── useAdminData.js          ← NEW: 統一 admin API 呼叫
│
├── admin-dashboard/                 ← NEW: 統一管理面板 SPA
│   ├── index.html
│   ├── main.js
│   ├── App.vue                      ← Tab bar + KeepAlive + auto-refresh
│   ├── style.css                    ← 統一樣式（合併兩個舊 style.css）
│   └── tabs/
│       ├── OverviewTab.vue          ← NEW: 總覽
│       ├── PerformanceTab.vue       ← 從 App.vue 拆出查詢效能+連線池
│       ├── CacheTab.vue             ← 從 App.vue 拆出 Redis+ProcessCache+RouteCache
│       ├── WorkerTab.vue            ← 從 App.vue 拆出 RQ+MemoryGuard+Storage+Control
│       ├── UsageTab.vue             ← 從 usage-kpi App.vue 遷入
│       └── LogsTab.vue              ← 從 App.vue 拆出系統日誌
│
├── admin-performance/               ← 保留（deprecated）
├── admin-user-usage-kpi/            ← 保留（deprecated）
│
├── admin-user-usage-kpi/components/ ← 遷入 UsageTab 使用
│   ├── KpiCard.vue                  ← 保留原位，UsageTab import
│   ├── DauTrendChart.vue
│   ├── HourlyLoginChart.vue
│   ├── DurationDistChart.vue
│   ├── TopUsersTable.vue
│   ├── DeptBreakdownTable.vue
│   └── RecentSessionsTable.vue
```

### Tab 切換流程

```
App.vue
  │
  ├── TabBar (activeTab state)
  │     [總覽] [效能] [快取] [Worker] [用戶] [日誌]
  │
  ├── <KeepAlive>
  │     <component :is="currentTabComponent" ref="tabRef" />
  │   </KeepAlive>
  │
  └── useAutoRefresh(30000, () => tabRef.value?.refresh?.())
        │
        └── watch(activeTab, () => nextTick(() => tabRef.value?.refresh?.()))
```

### 「總覽」Tab 佈局

```
┌────────────────────────────────────────────────────────┐
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│ │ Database │ │  Redis   │ │ Circuit  │ │  Memory  │  │
│ │   ● OK   │ │  ● OK    │ │ Breaker  │ │  62% ▓▓░ │  │
│ │  12ms    │ │  3ms     │ │  ● CLOSED│ │  4.2 GB  │  │
│ └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
│                                                        │
│ ⚠️ RQ dead worker alert: queue_depth=3 but 0 workers  │ ← 條件式 banner
│                                                        │
│ ┌─────────────────────┐ ┌─────────────────────┐      │
│ │ 查詢延遲 (30min)     │ │ 連線池飽和度 (30min)  │      │
│ │ ▁▂▃▄▅▆▇█▇▅▃▂▁      │ │ ▁▁▁▂▃▂▁▁▁▁          │      │
│ │ P95: 125ms          │ │ 最高: 45%            │      │
│ └─────────────────────┘ └─────────────────────┘      │
│                                                        │
│ ┌─────────────────────┐ ┌─────────────────────┐      │
│ │ Worker 記憶體 (30min) │ │ Cache 命中率 (30min)  │      │
│ │ ▁▂▃▄▅▆▇█▇▅▃▂▁      │ │ ▇▇▇▇▆▇▇▇▇▇          │      │
│ │ 峰值: 776 MB        │ │ L1: 98.2%           │      │
│ └─────────────────────┘ └─────────────────────┘      │
│                                                        │
│ ┌──────────────────────────────────────────────────┐  │
│ │ Active Alerts                                     │  │
│ │ • Redis unavailable, running in fallback mode     │  │
│ │ • Database pool saturation is high (92%)          │  │
│ └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

## File Impact

### New Files
| File | Purpose |
|------|---------|
| `frontend/src/admin-dashboard/index.html` | 新 SPA HTML 入口 |
| `frontend/src/admin-dashboard/main.js` | Vue app 初始化 |
| `frontend/src/admin-dashboard/App.vue` | Tab bar + KeepAlive + auto-refresh 控制 |
| `frontend/src/admin-dashboard/style.css` | 統一樣式 |
| `frontend/src/admin-dashboard/tabs/OverviewTab.vue` | 總覽 Tab |
| `frontend/src/admin-dashboard/tabs/PerformanceTab.vue` | 效能 Tab |
| `frontend/src/admin-dashboard/tabs/CacheTab.vue` | 快取 Tab |
| `frontend/src/admin-dashboard/tabs/WorkerTab.vue` | Worker Tab |
| `frontend/src/admin-dashboard/tabs/UsageTab.vue` | 用戶 Tab |
| `frontend/src/admin-dashboard/tabs/LogsTab.vue` | 日誌 Tab |
| `frontend/src/admin-shared/components/StatusDot.vue` | 共用狀態圓點 |
| `frontend/src/admin-shared/components/StatCard.vue` | 共用數值卡片 |
| `frontend/src/admin-shared/components/GaugeBar.vue` | 共用 Gauge 條 |
| `frontend/src/admin-shared/components/TrendChart.vue` | 共用趨勢圖 |
| `frontend/src/admin-shared/composables/useAdminData.js` | 統一 API 資料層 |

### Modified Files
| File | Changes |
|------|---------|
| `frontend/vite.config.js` | 新增 `admin-dashboard` 入口 |
| `src/mes_dashboard/routes/admin_routes.py` | 新增 `/admin/dashboard` 路由 serve 新 SPA HTML |
| `frontend/src/admin-performance/App.vue` | import 改為從 admin-shared 引入共用元件 |
| `frontend/src/admin-performance/components/` | 4 個元件移至 admin-shared（原位保留 re-export） |
