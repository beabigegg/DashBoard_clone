## Why

製程工程師目前在「報廢歷史查詢」可做回顧分析，但缺少以良率為主軸的前置異常偵測入口。`ERP_WIP_MOVETXN` 與 `ERP_WIP_MOVETXN_DETAIL` 已可作為良率基底來源，若不建立獨立能力，使用者需要在多工具間手動比對，追溯成本高且反應慢。

同時，良率異常判讀後仍需回到報廢細節資料做原因分析，因此需要一個可驗證、可重現的跨資料源映射機制，而不是把告警邏輯直接混入既有報廢查詢頁。

## What Changes

- 新增獨立功能「Yield Alert Center」，提供良率異常監看與清單化檢視（不改寫既有報廢歷史頁面主流程）。
- 新增後端查詢能力：以 `ERP_WIP_MOVETXN` / `ERP_WIP_MOVETXN_DETAIL` 為良率計算與異常候選來源。
- 新增回鑽能力：從告警項目連到報廢歷史細節，採用 `日期 + 工單 + 原因碼` 為主鍵，並納入原因碼正規化規則。
- 新增效能與穩定性邊界：查詢時間區間限制、結果快取與必要監控，避免高基數查詢拖垮服務。
- 保持既有「報廢歷史查詢」行為不變；本變更屬於額外新功能開發，非破壞式改版。

## Capabilities

### New Capabilities
- `yield-alert-center-page`: 提供良率異常清單、時間趨勢與 drilldown 入口的前端頁面能力。
- `yield-alert-center-api`: 提供基於 ERP 移轉/報廢資料的良率彙整與異常候選 API。
- `erp-reject-history-linkage`: 定義 ERP 良率基底資料與報廢歷史細節資料的鍵值映射與正規化契約。

### Modified Capabilities
- None.

## Impact

- Affected specs: 新增 `yield-alert-center-page`、`yield-alert-center-api`、`erp-reject-history-linkage` 規格。
- Affected code (expected):
  - Frontend: 導覽選單、Yield Alert Center 新頁面、圖表與 drilldown 互動。
  - Backend: 新 API 路由、服務層、Oracle 查詢與映射邏輯。
  - Data access: `ERP_WIP_MOVETXN`, `ERP_WIP_MOVETXN_DETAIL`, `DW_MES_LOTREJECTHISTORY` 讀取策略。
- Operational impact: Oracle 查詢負載增加；需以快取/時間窗限制與指標監控控制風險。
- Breaking changes: None.
