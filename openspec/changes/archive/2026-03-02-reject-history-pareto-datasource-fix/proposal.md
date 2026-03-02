## Why

報廢歷史柏拉圖的多個維度顯示不正確：package、type、equipment 全顯示 (NA)，workflow 顯示成 spec name，workcenter 維度應顯示 WORKCENTER_GROUP。原因是 SQL 資料來源選擇錯誤——目前錯誤地使用 `DW_MES_WIP` 作為 fallback，應改為正確使用 `DW_MES_CONTAINER` 取 package/type，`DW_MES_LOTWIPHISTORY` 取 workflow（透過 `WIPTRACKINGGROUPKEYID` 精確對應報廢事件），equipment 不做額外查找。

## What Changes

- 移除 `performance_daily.sql` 和 `performance_daily_lot.sql` 中的 `wip_lookup` CTE（來自 `DW_MES_WIP`）
- 新增 `LEFT JOIN DWH.DW_MES_LOTWIPHISTORY` 透過 `WIPTRACKINGGROUPKEYID` 取得報廢當下對應的 WORKFLOWNAME
- PJ_TYPE、PRODUCTLINENAME 還原為僅從 `DW_MES_CONTAINER` 取得
- EQUIPMENTNAME 還原為僅從 `DW_MES_LOTREJECTHISTORY` 取得（空就空，不額外查找）
- WORKFLOWNAME 改為從 `DW_MES_LOTWIPHISTORY` 取得（精確對應報廢事件的 WIP 步驟）
- 柏拉圖 workcenter 維度映射改回 `WORKCENTER_GROUP`（Python service 層）

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `reject-history-api`: Dimension Pareto 的 SQL 資料來源變更——移除 DW_MES_WIP fallback，改用 DW_MES_LOTWIPHISTORY 取 workflow，workcenter 維度映射改回 WORKCENTER_GROUP

## Impact

- SQL: `performance_daily.sql`, `performance_daily_lot.sql` — CTE 結構變更，JOIN 變更
- Python: `reject_dataset_cache.py`, `reject_history_service.py` — 維度映射常數調整
- 無前端變更、無 API 介面變更、無新增依賴
