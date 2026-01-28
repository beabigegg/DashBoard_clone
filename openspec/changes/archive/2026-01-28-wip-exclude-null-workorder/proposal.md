## Why

目前 WIP Overview 和 WIP Detail 的查詢會包含所有 `DWH.DW_PJ_LOT_V` 中的資料，包括 `WORKORDER` 為 NULL 的紀錄。這些 NULL WORKORDER 的紀錄通常是原物料（Raw Materials），不應該納入 WIP 統計計算。

將原物料納入計算會造成：
- WIP 總數被高估，無法反映真實生產中的 Lot 數量
- 各狀態（RUN/QUEUE/HOLD）的統計不準確
- Matrix 和 Detail 表格顯示非生產相關的資料，造成混淆

## What Changes

### 後端改動

1. **wip_service.py - `_build_base_conditions()` 函數**：
   - 新增預設條件 `WORKORDER IS NOT NULL`
   - 此條件會自動套用到所有 WIP 查詢（Summary、Matrix、Hold Summary、Detail、Meta APIs）

### 影響範圍

此改動會影響以下 API 的回傳資料：
- `/api/wip/overview/summary` - 排除原物料後的 WIP 統計
- `/api/wip/overview/matrix` - 排除原物料後的 Matrix
- `/api/wip/overview/hold` - 排除原物料後的 Hold Summary
- `/api/wip/detail/<workcenter>` - 排除原物料後的 Detail 資料
- `/api/wip/meta/workcenters` - 排除原物料後的 Workcenter 列表
- `/api/wip/meta/packages` - 排除原物料後的 Package 列表
- `/api/wip/meta/search` - 搜尋結果排除原物料

### 前端改動

- **無需修改**：前端直接使用後端回傳的資料，無需任何改動

## Capabilities

### Modified Capabilities

- `wip-service`: 在基礎查詢條件中排除 WORKORDER 為 NULL 的紀錄

## Impact

- **修改檔案**:
  - `src/mes_dashboard/services/wip_service.py` - 新增 `WORKORDER IS NOT NULL` 條件

- **無新增檔案**：僅修改一處

- **向後相容**：此為資料過濾邏輯調整，API 格式不變

- **風險評估**：低風險，僅排除不應顯示的原物料資料
