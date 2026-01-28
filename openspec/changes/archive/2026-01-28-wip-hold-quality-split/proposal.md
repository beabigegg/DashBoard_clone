## Why

目前 WIP Overview 和 WIP Detail 中的 HOLD 卡片將所有 Hold 原因混在一起顯示。但實務上，Hold 原因可分為兩類：

1. **品質異常 Hold**：需要品質工程師介入處理的問題（如：缺陷、不良率異常等）
2. **非品質異常 Hold**：流程性 Hold，不需品質介入（如：IQC 驗證、工程驗證、樣品留存等）

這兩類 Hold 的處理流程和優先級不同，混在一起會造成：
- 品質問題被淹沒在大量流程性 Hold 中
- 難以快速識別真正需要處理的品質異常
- Hold Summary 無法區分異常類型，無法有效分析

## What Changes

### WIP Overview 改動

1. **卡片拆分**：原本 1 張 HOLD 卡片 → 2 張獨立卡片
   - 「品質異常 Hold」卡片（紅色）
   - 「非品質異常 Hold」卡片（橙色）

2. **Hold Summary 標示**：在每個 Hold Reason 前面加入類型標籤
   - 品質異常：`[品質] Hold Reason Name`
   - 非品質異常：`[非品質] Hold Reason Name`

3. **篩選功能**：點擊拆分後的卡片可分別篩選
   - 點擊「品質異常 Hold」→ Matrix 只顯示品質異常 Hold
   - 點擊「非品質異常 Hold」→ Matrix 只顯示非品質異常 Hold

### WIP Detail 改動

1. **卡片拆分**：原本 1 張 HOLD 卡片 → 2 張獨立卡片
   - 「品質異常 Hold」卡片（紅色）
   - 「非品質異常 Hold」卡片（橙色）

2. **篩選功能**：點擊拆分後的卡片可分別篩選
   - 點擊「品質異常 Hold」→ Table 只顯示品質異常 Hold lots
   - 點擊「非品質異常 Hold」→ Table 只顯示非品質異常 Hold lots

### 後端 API 改動

1. **Summary API**：新增 `qualityHold` 和 `nonQualityHold` 分類統計
2. **Matrix API**：支援 `holdType` 參數（`quality` / `non-quality`）
3. **Hold Summary API**：新增 `holdType` 欄位標示每個 reason 的分類
4. **Detail API**：支援 `holdType` 參數篩選

### 非品質異常 Hold Reason 清單

以下 Hold Reason 歸類為「非品質異常」，其餘皆為「品質異常」：

- IQC檢驗(久存品驗證)(QC)
- 大中/安波幅50pcs樣品留樣(PD)
- 工程驗證(PE)
- 工程驗證(RD)
- 指定機台生產
- 特殊需求(X-Ray全檢)
- 特殊需求管控
- 第一次量產QC品質確認(QC)
- 需綁尾數(PD)
- 樣品需求留存打樣(樣品)
- 盤點(收線)需求

## Capabilities

### Modified Capabilities

- `wip-overview`: 拆分 HOLD 卡片為品質/非品質異常，Hold Summary 加入類型標示
- `wip-detail`: 拆分 HOLD 卡片為品質/非品質異常，支援分別篩選
- `wip-service`: API 新增 Hold 類型分類邏輯和篩選參數

## Impact

- **修改檔案**:
  - `src/mes_dashboard/templates/wip_overview.html` - 卡片拆分、Hold Summary 改版
  - `src/mes_dashboard/templates/wip_detail.html` - 卡片拆分
  - `src/mes_dashboard/services/wip_service.py` - 新增 Hold 分類邏輯
  - `src/mes_dashboard/routes/wip_routes.py` - 新增 API 參數

- **無新增檔案**：所有改動皆在現有檔案中進行

- **向後相容**：現有 API 參數保持不變，新增參數為可選
