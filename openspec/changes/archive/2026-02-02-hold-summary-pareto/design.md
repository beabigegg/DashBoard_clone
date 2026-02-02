## Context

WIP Overview 頁面目前以表格呈現 Hold Summary，資料來自 `/api/wip/overview/hold` API，回傳包含 `holdType: 'quality' | 'non-quality'` 分類。現有實作使用 `renderHold()` 函數動態產生表格 HTML。

專案已整合 ECharts 圖表庫（`/static/js/echarts.min.js`），在 `resource_history.html` 有完整使用範例。

## Goals / Non-Goals

**Goals:**
- 以柏拉圖呈現 Hold 分佈，快速辨識主要原因
- 分離品質/非品質異常為兩張獨立圖表
- 保留 drill-down 至 Hold Detail 頁面功能
- 在圖表下方提供摘要表格顯示精確數據

**Non-Goals:**
- 不修改後端 API（資料結構已足夠）
- 不新增其他圖表類型
- 不改變 Hold Detail 頁面

## Decisions

### 1. 圖表庫選擇：使用 ECharts

**決定**：沿用專案已整合的 ECharts

**理由**：
- 已在 `resource_history.html` 驗證可行
- 無需額外依賴
- 支援 bar + line 組合圖（柏拉圖標準呈現）

### 2. 資料分組策略：前端過濾

**決定**：在前端使用 `filter()` 按 `holdType` 分組

**理由**：
- API 已回傳 `holdType` 欄位
- 避免增加後端 API 複雜度
- 資料量小（通常 < 50 筆），前端處理無效能疑慮

### 3. 累計百分比計算：以 QTY 為基準

**決定**：柏拉圖 Y 軸顯示 QTY，累計線以 QTY 累計百分比計算

**理由**：
- QTY 更能反映實際影響規模
- 柱狀圖與累計線使用相同基準（QTY），圖表邏輯一致
- Lots 數量僅在下方摘要表格作為參考資訊呈現

### 4. Drill-down 實作：ECharts click 事件

**決定**：使用 ECharts `on('click')` 事件導向 Hold Detail 頁面

**理由**：
- 與現有表格連結行為一致
- 使用者可點擊柱狀圖或摘要表格連結

### 5. 版面配置：兩欄並排

**決定**：品質異常與非品質異常柏拉圖並排顯示

**理由**：
- 便於同時比較兩類 Hold 分佈
- 螢幕空間利用率高
- 響應式設計在小螢幕改為垂直堆疊

## Risks / Trade-offs

| 風險 | 緩解措施 |
|------|----------|
| X 軸標籤過長被截斷 | 設定 `axisLabel.rotate: 45` 並限制最大字元數 |
| 某分類無資料時顯示空白 | 顯示「目前無資料」提示訊息 |
| 響應式設計複雜度 | 使用 CSS Grid 配合 media query |
| 累計線在少量資料時跳躍明顯 | 可接受，這是柏拉圖正常特性 |
