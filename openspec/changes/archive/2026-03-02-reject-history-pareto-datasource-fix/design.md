## Context

報廢歷史查詢的 SQL 基底查詢（`performance_daily.sql` / `performance_daily_lot.sql`）目前有一個 `wip_lookup` CTE，從 `DW_MES_WIP`（8000 萬筆）以 `ROW_NUMBER()` + `CONTAINERID` 取最新一筆 WIP 記錄，用於 PJ_TYPE、PRODUCTLINENAME、EQUIPMENTS、WORKFLOWNAME 的 fallback。此做法存在多項問題：

1. `DW_MES_WIP` 取的是「最新」WIP 步驟，不是報廢發生當下的步驟
2. PJ_TYPE 和 PRODUCTLINENAME 應直接從 `DW_MES_CONTAINER` 取得
3. EQUIPMENTNAME 若 reject history 沒有值就應留空，不需額外查找
4. WORKFLOWNAME 應從 `DW_MES_LOTWIPHISTORY` 透過 `WIPTRACKINGGROUPKEYID` 精確對應

## Goals / Non-Goals

**Goals:**
- 修正 5 個維度柏拉圖的資料來源，使 package/type/workflow/equipment 正確顯示
- workcenter 柏拉圖維度維持使用 WORKCENTER_GROUP
- WORKFLOW 精確對應到報廢發生當下的 WIP 步驟

**Non-Goals:**
- 不變更前端元件邏輯
- 不變更 API 介面或回應結構
- 不新增篩選維度

## Decisions

### D1: 移除 `wip_lookup` CTE，改用直接 LEFT JOIN `DW_MES_LOTWIPHISTORY`

移除整個 `wip_lookup` CTE（來自 `DW_MES_WIP`），在 `reject_raw` 的 FROM 區段新增：

```sql
LEFT JOIN DWH.DW_MES_LOTWIPHISTORY lwh
  ON lwh.WIPTRACKINGGROUPKEYID = r.WIPTRACKINGGROUPKEYID
```

理由：`DW_MES_LOTREJECTHISTORY` 和 `DW_MES_LOTWIPHISTORY` 都有 `WIPTRACKINGGROUPKEYID`，兩邊都有索引，直接 JOIN 即可精確對應到報廢事件所在的 WIP 步驟。不需要 CTE、不需要 ROW_NUMBER、不需要子查詢。

### D2: 各欄位來源

| 欄位 | 來源表 | 寫法 |
|---|---|---|
| PJ_TYPE | DW_MES_CONTAINER | `NVL(TRIM(c.PJ_TYPE), '(NA)')` |
| PRODUCTLINENAME | DW_MES_CONTAINER | `NVL(TRIM(c.PRODUCTLINENAME), '(NA)')` |
| EQUIPMENTNAME | DW_MES_LOTREJECTHISTORY | `NVL(TRIM(r.EQUIPMENTNAME), '(NA)')` |
| PRIMARY_EQUIPMENTNAME | DW_MES_LOTREJECTHISTORY | `NVL(TRIM(REGEXP_SUBSTR(r.EQUIPMENTNAME, '[^,]+', 1, 1)), '(NA)')` |
| WORKFLOWNAME | DW_MES_LOTWIPHISTORY | `NVL(TRIM(lwh.WORKFLOWNAME), '(NA)')` |
| WORKCENTERNAME | spec_map (既有) | `NVL(TRIM(sm.WORK_CENTER), NVL(TRIM(r.WORKCENTERNAME), '(NA)'))` |
| WORKCENTER_GROUP | spec_map (既有) | `NVL(TRIM(sm.WORKCENTER_GROUP), NVL(TRIM(r.WORKCENTERNAME), '(NA)'))` |

### D3: Python 維度映射 workcenter 改回 WORKCENTER_GROUP

`reject_dataset_cache.py` 的 `_DIM_TO_DF_COLUMN` 和 `reject_history_service.py` 的 `_DIMENSION_COLUMN_MAP` 中 `"workcenter"` 映射改回 `WORKCENTER_GROUP` / `b.WORKCENTER_GROUP`。

### D4: 兩支 SQL 同步修改

`performance_daily.sql` 和 `performance_daily_lot.sql` 需同步做相同變更，保持一致。

## Risks / Trade-offs

- `DW_MES_LOTWIPHISTORY` 有 5400 萬筆，但 `WIPTRACKINGGROUPKEYID` 有索引，JOIN 效率可控
- 若 `WIPTRACKINGGROUPKEYID` 為 NULL 的 reject 記錄，WORKFLOWNAME 會顯示 (NA)——這是正確行為
- `DW_MES_CONTAINER` 的 PJ_TYPE / PRODUCTLINENAME 若為 NULL，仍會顯示 (NA)——這代表該 container 確實沒有此資訊
