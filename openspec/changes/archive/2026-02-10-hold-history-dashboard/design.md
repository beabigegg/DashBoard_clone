## Context

Hold Overview (DW_MES_LOT_V, Redis cache) 提供即時快照；Hold Detail 深入單一 Reason。但主管缺乏歷史視角——趨勢、時長分析、部門績效都只能透過 BI 工具 (PJMES043) 手動操作。

本設計在既有 Dashboard 架構上新增一個歷史績效頁面，直接查詢 `DWH.DW_MES_HOLDRELEASEHISTORY` 表 (~310K rows)，搭配 Redis 快取加速近期資料。

## Goals / Non-Goals

**Goals:**
- 提供自由日期區間的 Hold 歷史每日趨勢圖（On Hold/新增/解除/Future Hold）
- 提供 Reason Pareto、Duration 分布、負責人統計（部門+個人）分析
- 提供 paginated Hold/Release 明細表
- Reason Pareto 點擊可 cascade filter 負責人統計與明細表
- 近二月資料使用 Redis 快取（12hr TTL），前端切換 Hold Type 免 re-call

**Non-Goals:**
- 不替代既有 Hold Overview / Hold Detail 的即時功能
- 不引入即時 WebSocket 推送
- 不做跨頁面的 drill-through（本頁面自成體系）
- 不修改 HOLDRELEASEHISTORY 表結構或新增 index

## Decisions

### 1. 資料來源：直接查詢 HOLDRELEASEHISTORY vs. 預建聚合表

**選擇**: 直接查詢 + Redis 快取聚合結果

**理由**: 310K 行規模適中，calendar-spine cross-join 月級查詢在秒級內完成。預建聚合表增加 ETL 複雜度，且歷史數據變動低頻，12hr 快取已足夠。

**替代方案**: 在 DWH 建立物化視圖 → 拒絕，因需 DBA 協調且 Dashboard 應盡量自包含。

### 2. 快取策略：近二月 Redis vs. 全量快取 vs. 無快取

**選擇**: 近二月（當月 + 前一月）Redis 快取，12hr TTL

**理由**: 多數使用者查看近期資料。近二月快取命中率高，超過二月的查詢較少且可接受直接 Oracle 查詢的延遲。全量快取浪費記憶體且過期管理複雜。

**Redis key**: `hold_history:daily:{YYYY-MM}`
**結構**: 一份快取包含 quality / non_quality / all 三種 hold_type 的每日聚合，前端切換免 API re-call。
**跨月查詢**: 後端從多個月快取中切出需要的日期範圍後合併回傳。

### 3. trend API 回傳三種 hold_type vs. 按需查詢

**選擇**: trend API 一次回傳三種 hold_type 的每日資料

**理由**: 趨勢是最常操作的圖表，切換 hold_type 應即時響應。三種 hold_type 資料已在同一份 Redis 快取中，回傳全部不增加 I/O，但大幅改善 UX。其餘 4 支 API (pareto/duration/department/list) 按 hold_type 過濾，因為它們的 payload 可能很大。

### 4. SQL 集中管理：sql/hold_history/ 目錄

**選擇**: SQL 檔案放在 `src/mes_dashboard/sql/hold_history/` 目錄

**理由**: 遵循既有 `sql/query_tool/`、`sql/dashboard/`、`sql/resource/`、`sql/wip/` 的集中管理模式。SQL 與 Python 分離便於 review 和維護。

**檔案規劃**:
- `trend.sql` — calendar-spine cross-join 每日聚合（翻譯自 hold_history.md）
- `reason_pareto.sql` — GROUP BY HOLDREASONNAME
- `duration.sql` — 已 release 的 hold 時長分布
- `department.sql` — GROUP BY HOLDEMPDEPTNAME / HOLDEMP
- `list.sql` — paginated 明細查詢

### 5. 商業邏輯：07:30 班別邊界

**選擇**: 忠實保留 hold_history.md 的班別邊界邏輯

**理由**: 這是工廠既有的日報定義，07:30 後的交易歸入隔天。偏離此定義會導致 Dashboard 數字與既有 BI 報表不一致。

**實作**: 在 SQL 層處理 (`CASE WHEN TO_CHAR(HOLDTXNDATE,'HH24MI') >= '0730' THEN TRUNC(HOLDTXNDATE) + 1 ELSE TRUNC(HOLDTXNDATE) END`)。

### 6. 前端架構

**選擇**: 獨立 Vue 3 SFC 頁面，複用 wip-shared composables

**元件規劃**:
- `App.vue` — 頁面主容器、狀態管理、API 呼叫
- `FilterBar.vue` — DatePicker + Hold Type radio
- `SummaryCards.vue` — 6 張 KPI 卡片
- `DailyTrend.vue` — ECharts 折線+柱狀混合圖
- `ReasonPareto.vue` — ECharts Pareto 圖（可點擊）
- `DurationChart.vue` — ECharts 橫向柱狀圖
- `DepartmentTable.vue` — 可展開的部門/個人統計表
- `DetailTable.vue` — paginated 明細表

### 7. Duration 分布的計算範圍

**選擇**: 僅計算已 Release 的 hold（RELEASETXNDATE IS NOT NULL）

**理由**: 仍在 hold 中的無法確定最終時長，納入會扭曲分布。明細表中仍顯示未 release 的 hold（以 SYSDATE 計算到目前時長）。

## Risks / Trade-offs

- **[HOLDTXNDATE 無 index]** → HOLDRELEASEHISTORY 僅有 HISTORYMAINLINEID 和 CONTAINERID 的 index。日期範圍查詢走 full table scan (~310K rows)。緩解：12hr Redis 快取 + 月級查詢粒度限制。若未來資料量成長，可考慮請 DBA 加 HOLDTXNDATE index。
- **[Calendar-spine cross-join 效能]** → 月曆骨幹 × 全表 cross join 是最重的查詢。緩解：Redis 快取近二月，超過二月直接查詢但接受較長 loading。
- **[Redis 快取一致性]** → 12hr TTL 意味資料最多延遲 12 小時。緩解：歷史資料本身就是 T-1 更新，12hr 延遲對管理決策無影響。
- **[明細表回傳 HOLDCOMMENTS/RELEASECOMMENTS]** → 文字欄位可能很長。緩解：前端 truncate 顯示，hover 看全文。
