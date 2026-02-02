## Why

WIP Overview 頁面的 Hold Summary 目前以表格呈現，難以快速辨識主要的 Hold 原因分佈。使用柏拉圖（Pareto）圖可以更直觀地顯示：哪些 Hold 原因佔據最多比例，並透過累計百分比線幫助識別 80/20 法則中的關鍵因素。

## What Changes

- 將 Hold Summary 從單一表格改為**兩張柏拉圖**：
  - 品質異常 Hold (Quality)
  - 非品質異常 Hold (Non-Quality)
- 每張柏拉圖包含：
  - Y 軸（左）：QTY 數量（柱狀圖）
  - Y 軸（右）：累計百分比（折線圖）
  - X 軸：Hold Reason 名稱
- 每張圖下方保留**摘要表格**顯示：Hold Reason、Lots、QTY、累計%（以 QTY 為基準）
- 保留 **Drill-down 功能**：點擊柏拉圖柱狀或表格連結可跳轉至 Hold Detail 頁面
- **移除**原本的單一表格呈現方式

## Capabilities

### New Capabilities

- `hold-pareto-chart`: 在 WIP Overview 頁面以柏拉圖呈現 Hold 資料分佈，支援品質/非品質分類與互動式 drill-down

### Modified Capabilities

_(無需修改現有 spec - API 已提供完整資料，僅前端視覺化變更)_

## Impact

- **前端**：`src/mes_dashboard/templates/wip_overview.html`
  - 加入 ECharts 圖表庫引用
  - 新增兩組 chart container 與摘要表格
  - 新增 `renderQualityPareto()`, `renderNonQualityPareto()` 函數
  - 移除原本的 `renderHold()` 表格邏輯
- **後端**：無變更（API `/api/wip/overview/hold` 已提供 `holdType` 分類）
- **依賴**：ECharts 已整合於專案（`/static/js/echarts.min.js`）
