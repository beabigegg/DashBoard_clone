## Problem

MES Dashboard 的管理面板目前分裂為兩個完全獨立的 Vue SPA：

1. **admin-performance** (`/admin/performance`) — 效能監控，包含系統狀態、查詢延遲、Redis/Cache/連線池、Worker 控制、日誌等，全部垂直堆疊在一個超長頁面（~500 行 template）。
2. **admin-user-usage-kpi** (`/admin/user-usage-kpi`) — 使用者 KPI，包含 DAU、登入時段、使用時長、Top 使用者等。

**核心問題：**

- **零整合**：兩個 SPA 各自有 `main.js`、`index.html`、`style.css`，沒有共用 layout、navigation 或 component library。無法在兩個面板間導航。
- **資訊過載**：admin-performance 把所有資訊塞在單一頁面，需捲動 10+ 螢幕。無分類導航、無 section 定位。
- **體驗不一致**：performance 有自動更新，usage-kpi 沒有。Loading 狀態、錯誤處理各做各的。
- **數據浪費**：後端 `/health` 回傳大量 resilience/circuit_breaker/system_memory 資料，但 portal-shell 的 HealthStatus 只用了二元狀態。
- **缺失功能**：
  - 無 cache hit/miss 趨勢（Phase 4 新增的 metrics 無前端展示）
  - 無 dead worker alert 前端展示
  - 無 endpoint-level 延遲分析
  - portal-shell sidebar 無法直接進入管理面板

## Appetite

Medium — 預計 3-4 個開發週期。前端為主，後端僅微調現有 API（不新增 API）。

## Solution

將兩個獨立 admin SPA 合併為單一 **Unified Admin Dashboard**，採用 Tab-based navigation：

```
┌─────────────────────────────────────────────────────────┐
│  Admin Dashboard                          [自動更新 30s] │
│  ┌─────────────────────────────────────────────────┐    │
│  │ [總覽] [效能] [快取] [Worker] [用戶] [日誌]       │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  每個 Tab 為獨立 Vue component，按需載入                  │
│  共用 StatCard / GaugeBar / TrendChart / StatusDot      │
│  統一自動更新、Loading skeleton、錯誤處理                 │
└─────────────────────────────────────────────────────────┘
```

### Tab 內容規劃

| Tab | 來源 | 內容 |
|-----|------|------|
| 總覽 | 新建 | 4 狀態卡 + mini 趨勢 + active alerts + dead worker banner |
| 效能 | 從 performance 拆出 | P50/P95/P99 + 延遲趨勢 + 連線池 |
| 快取 | 從 performance 拆出 | Redis + ProcessLevelCache + Route Cache + hit/miss 趨勢 |
| Worker | 從 performance 拆出 | RQ workers/queues + memory guard + 控制面板 + 儲存管理 |
| 用戶 | 從 usage-kpi 遷入 | DAU/hourly/duration/top users/dept/recent sessions |
| 日誌 | 從 performance 拆出 | 系統日誌篩選/搜尋/分頁 |

### 不做（Rabbit Holes）

- 不新增後端 API — 所有資料已由 `/api/system-status`、`/api/metrics`、`/api/performance-detail`、`/api/performance-history`、`/api/user-usage-kpi` 等提供
- 不做 WebSocket 即時推送 — 30s polling 已足夠
- 不整合進 portal-shell SPA — admin 仍為獨立入口（`/admin/dashboard`），但 portal-shell sidebar 增加連結
- 不重寫 TrendChart/GaugeBar — 提升為共用元件，不改功能
