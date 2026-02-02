## 1. 準備工作

- [x] 1.1 在 wip_overview.html 加入 ECharts 腳本引用
- [x] 1.2 新增柏拉圖容器 HTML 結構（品質/非品質兩組 chart + 表格）

## 2. 資料處理函數

- [x] 2.1 實作 `splitHoldByType()` 函數，將 Hold 資料按 holdType 分為品質/非品質兩組
- [x] 2.2 實作 `prepareParetoData()` 函數，按 QTY 降序排列並計算累計百分比

## 3. 柏拉圖渲染

- [x] 3.1 實作 `initParetoCharts()` 函數，初始化兩個 ECharts 實例
- [x] 3.2 實作 `renderParetoChart()` 函數，配置柏拉圖選項（bar + line 組合圖）
- [x] 3.3 加入 ECharts click 事件處理，實作 drill-down 導向 Hold Detail 頁面
- [x] 3.4 處理無資料情況，顯示「目前無資料」提示

## 4. 摘要表格

- [x] 4.1 實作 `renderParetoTable()` 函數，渲染摘要表格（Reason、Lots、QTY、累計%）
- [x] 4.2 表格 Hold Reason 欄位加入 drill-down 連結

## 5. 樣式與響應式

- [x] 5.1 新增柏拉圖區塊 CSS 樣式
- [x] 5.2 實作響應式設計：大螢幕並排、小螢幕堆疊
- [x] 5.3 加入 window resize 事件處理，重新調整圖表尺寸

## 6. 整合與清理

- [x] 6.1 修改 `loadHold()` 呼叫新的渲染函數
- [x] 6.2 移除原本的 `renderHold()` 表格函數及相關 HTML/CSS
- [x] 6.3 測試驗證：資料載入、圖表渲染、drill-down 功能、響應式切換
