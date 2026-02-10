## Context

MES Dashboard 已有 WIP Overview（全局 RUN/QUEUE/HOLD 概況）和 Hold Detail（單一 Hold Reason 明細）。主管需要一個專用頁面，聚焦在 Hold Lot 的全局分析。

現有架構：Vue 3 SFC + Flask + Oracle（DWH.DW_MES_LOT_V），使用 Redis cache + snapshot indexes 加速查詢。經審計，wip_service.py 中已有大量可複用的函數和 cache 基礎設施：

**可直接呼叫**:
- `get_wip_matrix(status='HOLD', hold_type=...)` — Matrix 查詢，零改動
- `_select_with_snapshot_indexes(status='HOLD', hold_type=...)` — 已有 `wip_status['HOLD']` 和 `hold_type['quality'|'non-quality']` snapshot indexes
- `_get_wip_dataframe()` — L1 process cache (30s) → L2 Redis cache，`AGEBYDAYS` 欄位已在 View 中預先計算

**可擴充（向後相容）**:
- `get_hold_detail_summary(reason)` — 已有 totalLots/totalQty/avgAge/maxAge/workcenterCount，reason 改 optional 即可
- `get_hold_detail_lots(reason, ...)` — 已有完整分頁邏輯 + workcenter/package/age_range 過濾，reason 改 optional + 加 hold_type 即可

**前端可直接 import**:
- `hold-detail/SummaryCards.vue` — props `{ totalLots, totalQty, avgAge, maxAge, workcenterCount }` 完全相容
- `wip-shared/Pagination.vue`、`useAutoRefresh`、`core/api.js`、`wip-shared/constants.js`

## Goals / Non-Goals

**Goals:**
- 提供主管一覽各站 Hold Lot 情況的獨立頁面
- TreeMap 視覺化讓嚴重程度一目了然（面積=QTY，顏色=滯留天數）
- Matrix + TreeMap + Table 三層 cascade 篩選，互動流暢
- 預設品質異常 Hold，可切換
- 最大化複用現有 service 函數、cache 基礎設施和前端元件

**Non-Goals:**
- 不取代或修改現有 Hold Detail 頁面（擴充 service 函數需向後相容）
- 不新增資料庫 view 或 table — 完全複用 DWH.DW_MES_LOT_V
- 不新增 SQL 模板 — 複用現有 summary.sql / matrix.sql / detail.sql + QueryBuilder WHERE clause
- 不實作 autocomplete 搜尋（篩選僅 Hold Type + Reason dropdown）
- 不實作 Lot 點擊展開的 detail panel（明細表為純展示）

## Decisions

### D1: 擴充現有 service 函數，非新建

**決定**: 擴充 `get_hold_detail_summary()` 和 `get_hold_detail_lots()` 的參數簽名，而非建立新的 `get_hold_overview_summary()` / `get_hold_overview_lots()`。唯一全新的函數是 `get_hold_overview_treemap()`（WC × Reason 聚合邏輯不存在於現有函數）。

**擴充方式**:
- `get_hold_detail_summary(reason)` → `get_hold_detail_summary(reason=None, hold_type=None)`
  - `reason=None` 時聚合所有 HOLD lots
  - `hold_type='quality'|'non-quality'` 進一步過濾
  - 原有 Hold Detail 呼叫 `get_hold_detail_summary(reason='xxx')` 行為不變
- `get_hold_detail_lots(reason, ...)` → `get_hold_detail_lots(reason=None, hold_type=None, treemap_reason=None, ...)`
  - `reason=None` 時返回所有 HOLD lots
  - `treemap_reason` 支援 TreeMap 點擊篩選
  - 現有 Hold Detail 呼叫簽名不受影響

**理由**: 這兩個函數的核心邏輯（cache path + Oracle fallback + 分頁 + 過濾）完全相同，差異僅在 reason 是否為必填。新建函數會複製 80%+ 相同邏輯，增加維護負擔。

**替代方案**: 新建獨立函數 — 但會造成大量重複的 cache 查詢路徑和 Oracle fallback 邏輯。

### D2: Matrix API 直接呼叫 get_wip_matrix，僅擴充 reason 參數

**決定**: Hold Overview 的 Matrix API 直接呼叫現有 `get_wip_matrix(status='HOLD', hold_type=...)` 函數。唯一需要擴充的是新增 optional `reason` 參數，支援 Filter Bar 的 Reason 篩選。

**理由**: `get_wip_matrix` 已支援 `status` 和 `hold_type` 參數，能完全滿足 Hold Overview Matrix 的需求。擴充 reason 參數的改動量極小，且 reason=None 時行為與現有完全一致。

**替代方案**: 複製 matrix 邏輯到新函數 — 違反 DRY，且 matrix 排序/分頁邏輯會分散維護。

### D3: TreeMap 聚合是唯一需要全新建立的 service 函數

**決定**: 新增 `get_hold_overview_treemap()` 函數，後端返回已聚合的 `{ workcenter, reason, qty, lots, avgAge }` 陣列。此函數使用與其他函數相同的 `_select_with_snapshot_indexes()` + Oracle fallback 模式。

**理由**: 現有函數都沒有「按 (WORKCENTER_GROUP, HOLDREASONNAME) 二維聚合」的邏輯。這是 TreeMap 視覺化特有的需求，值得獨立建立。Hold Lot 可能數千筆，前端 groupBy 聚合會造成不必要的資料傳輸和 CPU 開銷。

**替代方案**: 前端從 lots API 取全部資料後自行聚合 — 資料量大時效能差，且需一次載入所有 lot。

### D4: TreeMap 顏色映射使用固定 4 級色階

**決定**: 平均滯留天數映射到 4 個顏色等級：
- `< 1 天` → 綠色 (#22c55e)
- `1-3 天` → 黃色 (#eab308)
- `3-7 天` → 橙色 (#f97316)
- `> 7 天` → 紅色 (#ef4444)

ECharts TreeMap 使用 `visualMap` 組件實現連續色階。

**理由**: 與 Hold Detail 的 Age Distribution 分段一致（0-1, 1-3, 3-7, 7+），主管認知模型統一。

### D5: Filter cascade 為前端狀態管理，不影響 Summary 和 Matrix 的 API 呼叫

**決定**:
- Filter Bar（Hold Type / Reason）變更 → 呼叫全部 4 支 API
- Matrix 點擊 → 前端設定 `matrixFilter`，僅呼叫 treemap + lots API
- TreeMap 點擊 → 前端設定 `treemapFilter`，僅呼叫 lots API

**理由**: Summary 和 Matrix 反映全局數據，不應被 Matrix/TreeMap 的 drilldown 操作影響。這與 WIP Overview 的 StatusCards 不影響 Summary 的模式一致。

### D6: 路由結構與 Blueprint 獨立

**決定**: 新建 `hold_overview_routes.py` 作為獨立 Blueprint（`hold_overview_bp`），路由前綴 `/api/hold-overview/`。頁面路由 `GET /hold-overview` 由此 Blueprint 提供。

**理由**: 與 `hold_routes.py`（Hold Detail）和 `wip_routes.py`（WIP Overview）平行，職責分離。

### D7: 前端元件複用策略 — import > 擴充 > 新建

**決定**:

| 元件 | 策略 | 理由 |
|------|------|------|
| `hold-detail/SummaryCards.vue` | **直接 import** | props 形狀 `{ totalLots, totalQty, avgAge, maxAge, workcenterCount }` 完全相容 |
| `wip-shared/Pagination.vue` | **直接 import** | 已由 hold-detail/LotTable 使用，通用元件 |
| `wip-overview/MatrixTable.vue` | **參考新建 `HoldMatrix.vue`** | 需要 cell click + column click + active highlight — 原有只有 row drilldown，改動幅度大不適合直接修改原件 |
| `hold-detail/LotTable.vue` | **參考新建 `LotTable.vue`** | 需加 Hold Reason 欄位 + 移除 Spec 欄位 — hold-detail 不需要 reason 欄（已在 URL 參數中），直接修改會破壞現有頁面 |
| `HoldTreeMap.vue` | **全新** | 無現有 TreeMap 元件 |
| `FilterBar.vue` | **全新** | Hold Type radio + Reason dropdown 是此頁獨有的 UI |
| `FilterIndicator.vue` | **全新** | cascade filter 指示器是此頁獨有的 UI |

**理由**: 直接修改跨頁面共用的元件有破壞現有頁面的風險。props 完全相容的元件直接 import；需要結構性改動的元件則基於現有程式碼新建，保留一致的 coding pattern 但避免耦合。

### D8: ECharts TreeMap 模組 tree-shaking

**決定**: 前端使用 `import { TreemapChart } from 'echarts/charts'` 按需導入，搭配現有 `vendor-echarts` chunk。

**理由**: 現有 ECharts vendor chunk 已包含 BarChart、LineChart 等。TreemapChart 加入後仍在同一 chunk，不增加額外 HTTP request。

## Risks / Trade-offs

- **[向後相容]** 擴充 `get_hold_detail_summary()` 和 `get_hold_detail_lots()` 簽名時，必須確保 reason 參數的預設行為不變 → 使用 `reason=None` 預設值，現有呼叫端傳入 reason 的行為完全不變；需補充單元測試覆蓋原有 Hold Detail 的呼叫路徑
- **[TreeMap 資料量]** 如果 Hold Reason 種類很多（>20），TreeMap 小區塊會難以辨識 → 可考慮只顯示 Top N reason，其餘歸為「其他」
- **[Matrix 與 TreeMap 同時篩選]** 使用者可能忘記已有 matrix 篩選，誤以為 TreeMap 是全局 → 需要明確的 active filter 指示器和一鍵清除功能
- **[ECharts TreeMap 效能]** 大量區塊時 TreeMap 渲染可能卡頓 → ECharts TreeMap 有內建 leafDepth 限制，測試時注意超過 200 個葉節點的情境
- **[Cache 一致性]** Hold Overview 與 WIP Overview 共用同一份 cache，auto-refresh 週期相同（10 分鐘），不需調整 cache 策略
