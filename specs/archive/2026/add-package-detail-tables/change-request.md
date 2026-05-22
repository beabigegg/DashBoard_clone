# Change Request

## Original Request

補齊明細表缺少的產品資訊欄位（Package / PRODUCTLINENAME）：五個含 LOT ID 或 WORKORDER 的明細表目前未顯示封裝型號，需補齊前後端與匯出。受影響清單：
(1) hold-history 明細（DetailTable + 後端 SQL + 匯出）；
(2) query-tool Lot 歷史 tab（LotHistoryTable + lot_history.sql）；
(3) query-tool 機台生產紀錄（EquipmentLotsTable + equipment_lots.sql + 匯出）；
(4) query-tool 機台報廢紀錄（EquipmentRejectsTable，SQL 已有 PRODUCTLINENAME 但前端未顯示，確認匯出也一起補）；
(5) 原物料用量明細（material-consumption DetailTable + 後端 SQL + 匯出）。
所有 SQL 都已 JOIN DW_MES_CONTAINER，只需補 SELECT c.PRODUCTLINENAME；前端各自在 COLUMN_DEFS / 表頭補上 Package 欄；匯出 CSV/Excel 也需同步加入此欄。

## Business / User Goal

## Non-goals

## Constraints

## Known Context

## Open Questions

## Requested Delivery Date / Priority
