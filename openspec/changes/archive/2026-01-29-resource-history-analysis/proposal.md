## Why

目前缺乏機台歷史效能的深度分析工具。使用者需要：

- 分析各站點、各型號的歷史稼動率趨勢
- 了解 SEMI E10 設備狀態（PRD、SBY、UDT、SDT、EGT、NST）的時間分布
- 支援日/週/月/年等多時間粒度的效能分析
- 從站點下鑽至型號、再到個別機台的詳細數據

## What Changes

### 新增機台歷史表現分析頁面

建立完全獨立的歷史分析頁面 `/resource-history`，提供：

1. **篩選條件區**
   - 日期範圍選擇器
   - 時間粒度切換（日/週/月/年）
   - 站點（Workcenter）下拉選單
   - 機台型號（Resource Family）下拉選單
   - 查詢按鈕（預設不載入資料，需使用者主動觸發）

2. **KPI 摘要卡片**
   - OU%（整體稼動率）
   - PRD 時數（生產時間）
   - UDT/SDT/EGT 時數（各類停機時間）
   - 機台數量

3. **分析圖表**
   - OU% 趨勢折線圖（含時間軸）
   - E10 狀態堆疊長條圖（各狀態時數分布）
   - 工站 OU% 對比水平條形圖
   - 設備狀態熱力圖（站點 × 時間）

4. **明細表格**
   - 階層式展開：站點 → 型號 → 個別機台
   - 欄位：OU%、PRD（時數/佔比）、SBY（時數/佔比）、UDT（時數/佔比）、SDT（時數/佔比）、EGT（時數/佔比）、NST（時數/佔比）、機台數
   - 支援匯出功能

## Capabilities

### New Capabilities

- `resource-history-page`: 機台歷史表現分析頁面，包含篩選、KPI、圖表、明細表格
- `resource-history-service`: 歷史資料查詢服務，支援多維度聚合與階層式資料結構

### Modified Capabilities

- （無需修改現有 spec，/resource 頁面的調整為實作層級變更）

## Impact

- **新增檔案**:
  - `src/mes_dashboard/templates/resource_history.html` - 歷史分析頁面模板
  - `src/mes_dashboard/routes/resource_history_routes.py` - 歷史分析路由
  - `src/mes_dashboard/services/resource_history_service.py` - 歷史資料查詢服務

- **修改檔案**:
  - `src/mes_dashboard/__init__.py` - 註冊新路由

- **資料來源**:
  - `DW_MES_RESOURCESTATUS_SHIFT` - 機台狀態班別資料（約 74M 筆）
  - `DW_MES_RESOURCE` - 機台維度資料

- **向後相容**：本變更為純新增功能，不影響任何現有頁面
