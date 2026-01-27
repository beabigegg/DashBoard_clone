## Why

現有 WIP 報表使用 `DW_MES_WIP` 歷史表，需要複雜的 ROW_NUMBER() 計算來取得即時快照。IT 已建立新的即時 WIP View `DWH.DW_PJ_LOT_V`（5分鐘更新），可大幅簡化查詢並提供更完整的欄位資訊。需要重建 WIP Dashboard 以使用新資料來源，並建立兩種不同使用者導向的報表。

## What Changes

- **刪除** 現有 WIP 報表相關檔案 (`wip_report.html`, `wip_service.py` 中的舊查詢)
- **新增** WIP Overview Dashboard - 高階主管總覽
  - WORKCENTER_GROUP × PRODUCTLINENAME 矩陣 (顯示 QTY)
  - Hold 摘要表
  - 點擊工站可跳轉至 Detail
- **新增** WIP Detail Dashboard - 產線工站細部檢視
  - 依 WORKCENTER_GROUP 篩選
  - SPECNAME 橫向展開 (依 SPECSEQUENCE 排序)
  - 顯示 Lot、設備、狀態資訊
- **新增** 自動刷新機制
  - 前端每 10 分鐘無縫更新 (無整頁 reload)
  - 局部 DOM 更新避免畫面閃爍
- **移除** 老化分析相關功能 (AGEBYDAYS)

## Capabilities

### New Capabilities

- `wip-overview`: 高階主管 WIP 總覽 Dashboard - 工站×產品線矩陣、Hold 摘要、KPI 卡片
- `wip-detail`: 產線工站 WIP 細部 Dashboard - 單一工站的 Lot 明細、設備狀態、Spec 分布
- `wip-data-service`: WIP 資料查詢服務 - 使用 `DWH.DW_PJ_LOT_V` 作為資料來源的後端 API
- `auto-refresh`: 前端自動刷新機制 - 無縫更新 DOM、避免畫面閃爍

### Modified Capabilities

(無 - 完全新建，不修改現有 specs)

## Impact

- **刪除檔案**:
  - `src/mes_dashboard/templates/wip_report.html`
  - `src/mes_dashboard/templates/wip_overview.html` (若存在)
  - `src/mes_dashboard/services/wip_service.py` 中的舊查詢函數
  - `src/mes_dashboard/config/workcenter_groups.py` (改用 View 內建 WORKCENTER_GROUP)
- **新增檔案**:
  - `src/mes_dashboard/templates/wip_overview.html`
  - `src/mes_dashboard/templates/wip_detail.html`
  - `src/mes_dashboard/services/wip_service.py` (重寫)
  - `src/mes_dashboard/routes/wip.py` (新增路由)
- **資料來源**: `DW_MES_WIP` → `DWH.DW_PJ_LOT_V`
- **API 變更**: 新的 API endpoints 取代現有的
