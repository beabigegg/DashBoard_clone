-- WIP Detail Query
-- Returns paginated lot details for a specific workcenter group
--
-- Uses ROW_NUMBER() for efficient pagination
--
-- Parameters:
--   :offset - Starting row offset (0-based)
--   :limit - Number of rows to return
--
-- Dynamic placeholders:
--   WHERE_CLAUSE - Filter conditions

SELECT * FROM (
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
             ELSE 'QUEUE' END AS WIP_STATUS,
        ROW_NUMBER() OVER (ORDER BY LOTID) as RN
    FROM DWH.DW_MES_LOT_V
    {{ WHERE_CLAUSE }}
)
WHERE RN > :offset AND RN <= :offset + :limit
ORDER BY RN
