## Why

Hold 即時概況版面單薄（僅 FilterBar + SummaryCards + Matrix + LotTable），缺乏視覺密度且篩選能力有限（只有 holdType + reason）。而 WIP 即時概況承載了兩張 Hold 柏拉圖，但使用者分析 Hold 數據時需在兩頁間來回切換。此次重構將 Hold 相關視覺化集中到 Hold 即時概況，並統一篩選器與 Lot 明細欄位，讓兩頁各司其職。

## What Changes

- 將 WIP 即時概況的品質異常 / 非品質異常 Hold 柏拉圖移至 Hold 即時概況
- WIP 即時概況的「品質異常」「非品質異常」StatusCard 點擊由篩選 matrix 改為跳轉至 Hold 即時概況（帶 hold_type 參數）
- Hold 即時概況直接進入時 Hold Type 預設「全部」（原為「品質異常」）
- Hold 即時概況加入 WIP 即時概況的 6 欄位 FilterPanel（workorder/lotid/package/type/firstname/waferdesc）
- Hold Detail 返回按鈕改指 Hold 即時概況（原指 WIP 即時概況）
- 統一 Hold 即時概況與 Hold Detail 的 Lot 明細欄位（合併 Hold Reason + Spec 為 13 欄）
- Hold 即時概況版面修正（FilterBar 寬度過大、缺少 content-grid 包裹）
- 後端 Hold Overview API 穿透 WIP 篩選參數（workorder/lotid/type/firstname/waferdesc）

## Capabilities

### New Capabilities

_(無新增 capability)_

### Modified Capabilities

- `hold-overview-page`: Hold 即時概況加入柏拉圖、FilterPanel、預設 holdType 改為 all、版面修正、統一 LotTable
- `wip-overview-page`: 移除 Hold 柏拉圖、Hold 卡片改為跳轉導航
- `hold-detail-page`: 返回按鈕改指 Hold Overview、改用統一 LotTable

## Impact

- **前端**：`wip-overview/App.vue`（移除柏拉圖、卡片跳轉）、`hold-overview/App.vue`（核心重構）、`hold-detail/App.vue`（導航修正）、共用組件新增（ParetoSection 搬遷、HoldLotTable）、CSS 重構
- **後端**：`hold_overview_routes.py`（3 API 加入篩選參數）、`wip_service.py`（2 函式簽名擴充）、`hold_routes.py`（redirect 改向）
- **API**：`/api/hold-overview/summary`、`/api/hold-overview/matrix`、`/api/hold-overview/lots` 新增 workorder/lotid/type/firstname/waferdesc 可選參數（向後相容）
