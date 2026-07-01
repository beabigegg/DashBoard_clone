# Change Request

## Original Request

EAP-alarm coarse filter 擴充：新增 LOT_ID 直接輸入與 TYPE/PACKAGE/BOP 產品維度篩選，將這些維度加入 spool key 以直接縮減 Oracle EAP_EVENT 查詢量；機台改為可選（三種篩選維度至少一個必填）。

背景：DWH.EAP_EVENT 資料表過大，目前只能用日期+機台縮減查詢量。使用者需要能以特定 LOT ID 或產品維度（PJ_TYPE / PRODUCTLINENAME / PJ_BOP）搭配日期去鎖定查詢範圍。DWH.DW_MES_CONTAINER 的 CONTAINERNAME 欄位有 index（DW_C_CONTAINERNAME），對應 EAP_EVENT.LOT_ID，可以用 EXISTS semi-join 在 Oracle 層過濾。

## Business / User Goal

## Non-goals

## Constraints

## Known Context

## Open Questions

## Requested Delivery Date / Priority
