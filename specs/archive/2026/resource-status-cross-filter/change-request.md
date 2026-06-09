# Change Request

## Original Request

設備及時概況頁面 (resource-status) 中，各個圖都要有篩選功能，跟 PowerBI 一樣：點擊任何一個圖的元素（Ring chart 色塊、Heatmap 格子、Matrix 列、Alert 項目）後，頁面上其他所有圖都要同步縮小到該選取的範圍內。

## Business / User Goal

讓工廠工程師在設備及時概況頁面上可以快速從任一維度切入分析，不需要操作頂部 FilterBar，直接點圖即可 drill-in，提升分析效率。

## Non-goals

- 不加後端 API（所有資料已在前端 flat array，cross-filter 全部 client-side）
- 不改 FilterBar 的現有行為
- 不做跨頁面狀態同步

## Constraints

- 所有圖 (WorkcenterOuRings、OuHeatmap、MatrixSection、MaintenanceAlerts、EquipmentGrid) 已從同一個 flat equipment array 衍生資料
- MatrixSection 已有 matrixFilter click-to-filter 模式可參考
- CSS scoping 規則：所有 feature CSS 必須在 `.theme-resource-status` 下
- 不可改動 `shared-ui/` 元件的 emit/prop 介面（除非 additive）

## Known Context

- 頁面資料來源：`/api/resource/status` 一次載入全部 equipment records
- 現有篩選狀態管理：`useFilterOrchestrator` (top-level FilterBar) + `matrixFilter[]` + `summaryStatusFilter`（後兩者 client-side only）
- 4 個主要圖表元件：WorkcenterOuRings（ECharts ring）、OuHeatmap（table）、MatrixSection（階層表）、MaintenanceAlerts（排名清單）
- 已知 ECharts click 事件需要額外綁定才能捕捉 series/data name

## Open Questions

- 多圖同時有選取時的交集語意：AND（各圖選取取交集）還是只允許一個圖有選取？
- 「清除選取」的 UX：ESC 鍵、re-click、頁面固定按鈕？

## Requested Delivery Date / Priority

中優先，無硬性截止日。
