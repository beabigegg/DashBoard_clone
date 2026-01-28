## Why

目前 WIP Overview 的 Hold Summary 僅顯示各 Hold Reason 的統計數據，但缺乏深入分析的功能。當使用者想了解某個特定 Hold Reason 的詳細分佈時，需要手動到其他系統查詢，造成：

- 無法快速了解特定 Hold Reason 影響了哪些站群和封裝類型
- 無法分析 Hold 中的 lot 在當站滯留時間分佈
- 需要在多個系統間切換才能取得完整資訊

## What Changes

### 新增 Hold Detail 頁面

當使用者在 WIP Overview 的 Hold Summary 中點擊某個 Hold Reason，導向新的 Hold Detail 頁面，提供以下資訊：

1. **摘要卡片**
   - Total Lots：該 Hold Reason 的 lot 總數
   - Total QTY：總數量
   - 平均當站滯留：所有 lot 的平均滯留天數
   - 最久當站滯留：最長滯留天數
   - 影響站群：受影響的 workcenter 數量

2. **分佈分析表格**
   - By Workcenter：各站群的 lot 數、數量、百分比
   - By Package：各封裝類型的 lot 數、數量、百分比
   - 兩個表格皆可點擊篩選下方 Lot Details

3. **當站滯留天數分佈（Age Distribution）**
   - 0-1 天、1-3 天、3-7 天、7+ 天 四個分段
   - 每個分段顯示 lot 數、數量、百分比
   - 可點擊篩選下方 Lot Details

4. **Lot Details 表格**
   - 顯示所有符合條件的 lot 明細
   - 欄位：LOTID, WORKORDER, QTY, Package, Workcenter, Spec, Age, Hold By, Dept
   - 支援分頁功能
   - 顯示目前篩選狀態，可一鍵清除

### Hold Summary 連結

WIP Overview 的 Hold Summary 表格中，每個 Hold Reason 可點擊導向 Hold Detail 頁面。

## Capabilities

### New Capabilities

- `hold-detail`: 新頁面，顯示特定 Hold Reason 的詳細分佈分析

### Modified Capabilities

- `wip-overview`: Hold Summary 中的 Hold Reason 加入連結導向 Hold Detail 頁面

## Impact

- **新增檔案**:
  - `src/mes_dashboard/templates/hold_detail.html` - Hold Detail 頁面模板
  - `src/mes_dashboard/routes/hold_routes.py` - Hold Detail 路由

- **修改檔案**:
  - `src/mes_dashboard/templates/wip_overview.html` - Hold Summary 加入連結
  - `src/mes_dashboard/services/wip_service.py` - 新增 Hold Detail 相關查詢函數
  - `src/mes_dashboard/__init__.py` - 註冊新路由

- **向後相容**：現有功能不受影響
