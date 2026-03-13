-- Optimized: wip/detail
-- Change: Replaced ROW_NUMBER pagination with OFFSET...FETCH NEXT (Oracle 12c+)
--         Eliminates need for outer wrapper and full materialization
--
-- Parameters:
--   :offset - Starting row offset (0-based)
--   :limit - Number of rows to return
--
-- Dynamic placeholders:
--   WHERE_CLAUSE - Filter conditions

SELECT
    LOTID,
    EQUIPMENTS,
    STATUS,
    HOLDREASONNAME,
    QTY,
    PACKAGE_LEF,
    SPECNAME,
    CASE WHEN COALESCE(EQUIPMENTCOUNT, 0) > 0 THEN 'RUN'
         WHEN COALESCE(CURRENTHOLDCOUNT, 0) > 0 THEN 'HOLD'
         ELSE 'QUEUE' END AS WIP_STATUS
FROM DWH.DW_MES_LOT_V
{{ WHERE_CLAUSE }}
ORDER BY LOTID
OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY
