## 1. SQL 基底查詢修正 — performance_daily.sql

- [x] 1.1 移除 `wip_lookup` CTE（整個 DW_MES_WIP 相關區段）
- [x] 1.2 新增 `LEFT JOIN DWH.DW_MES_LOTWIPHISTORY lwh ON lwh.WIPTRACKINGGROUPKEYID = r.WIPTRACKINGGROUPKEYID`
- [x] 1.3 PJ_TYPE 還原為 `NVL(TRIM(c.PJ_TYPE), '(NA)')`
- [x] 1.4 PRODUCTLINENAME 還原為 `NVL(TRIM(c.PRODUCTLINENAME), '(NA)')`
- [x] 1.5 EQUIPMENTNAME 還原為 `NVL(TRIM(r.EQUIPMENTNAME), '(NA)')`，PRIMARY_EQUIPMENTNAME 同步還原
- [x] 1.6 WORKFLOWNAME 改為 `NVL(TRIM(lwh.WORKFLOWNAME), '(NA)')`

## 2. SQL 基底查詢修正 — performance_daily_lot.sql

- [x] 2.1 移除 `wip_lookup` CTE
- [x] 2.2 新增 `LEFT JOIN DWH.DW_MES_LOTWIPHISTORY lwh ON lwh.WIPTRACKINGGROUPKEYID = r.WIPTRACKINGGROUPKEYID`
- [x] 2.3 PJ_TYPE 還原為 `NVL(TRIM(c.PJ_TYPE), '(NA)')`
- [x] 2.4 PRODUCTLINENAME 還原為 `NVL(TRIM(c.PRODUCTLINENAME), '(NA)')`
- [x] 2.5 EQUIPMENTNAME 還原為 `NVL(TRIM(r.EQUIPMENTNAME), '(NA)')`，PRIMARY_EQUIPMENTNAME 同步還原
- [x] 2.6 WORKFLOWNAME 改為 `NVL(TRIM(lwh.WORKFLOWNAME), '(NA)')`

## 3. Python 維度映射修正

- [x] 3.1 `reject_dataset_cache.py` `_DIM_TO_DF_COLUMN` — workcenter 改回 `WORKCENTER_GROUP`
- [x] 3.2 `reject_history_service.py` `_DIMENSION_COLUMN_MAP` — workcenter 改回 `b.WORKCENTER_GROUP`
