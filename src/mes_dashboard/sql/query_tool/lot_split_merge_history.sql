-- Optimized: query_tool/lot_split_merge_history
-- Change: Converted OR IN to UNION ALL for separate index seeks
--         Original: CONTAINERID IN (...) OR FROMCONTAINERID IN (...)
--         OR condition prevents optimizer from using index on either column

WITH work_order_lots AS (
    SELECT CONTAINERID
    FROM DWH.DW_MES_CONTAINER
    WHERE {{ WORK_ORDER_FILTER }}
),
matched_records AS (
    -- Branch 1: target container matches work order
    SELECT
        h.HISTORYMAINLINEID,
        h.CDONAME AS OPERATION_TYPE,
        h.CONTAINERID AS TARGET_CONTAINERID,
        h.CONTAINERNAME AS TARGET_LOT,
        h.FROMCONTAINERID AS SOURCE_CONTAINERID,
        h.FROMCONTAINERNAME AS SOURCE_LOT,
        h.QTY AS TARGET_QTY,
        h.TXNDATE
    FROM DWH.DW_MES_HM_LOTMOVEOUT h
    WHERE h.CONTAINERID IN (SELECT CONTAINERID FROM work_order_lots)
      AND h.FROMCONTAINERID IS NOT NULL
      {{ TIME_WINDOW }}
    UNION ALL
    -- Branch 2: source container matches work order (exclude already matched)
    SELECT
        h.HISTORYMAINLINEID,
        h.CDONAME AS OPERATION_TYPE,
        h.CONTAINERID AS TARGET_CONTAINERID,
        h.CONTAINERNAME AS TARGET_LOT,
        h.FROMCONTAINERID AS SOURCE_CONTAINERID,
        h.FROMCONTAINERNAME AS SOURCE_LOT,
        h.QTY AS TARGET_QTY,
        h.TXNDATE
    FROM DWH.DW_MES_HM_LOTMOVEOUT h
    WHERE h.FROMCONTAINERID IN (SELECT CONTAINERID FROM work_order_lots)
      AND h.CONTAINERID NOT IN (SELECT CONTAINERID FROM work_order_lots)
      AND h.FROMCONTAINERID IS NOT NULL
      {{ TIME_WINDOW }}
)
SELECT *
FROM matched_records
ORDER BY TXNDATE
{{ ROW_LIMIT }}
