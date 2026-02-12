-- LOT Split/Merge History Query (拆併批歷史紀錄)
-- Query by CONTAINERID list from same work order
-- Check both TARGET (CONTAINERID) and SOURCE (FROMCONTAINERID) to find all related records
--
-- Parameters:
--   WORK_ORDER_FILTER - QueryBuilder filter on MFGORDERNAME
--   TIME_WINDOW - Optional time-window filter (default fast mode: 6 months)
--   ROW_LIMIT - Optional row limit (default fast mode: 500)

WITH work_order_lots AS (
    SELECT CONTAINERID
    FROM DWH.DW_MES_CONTAINER
    WHERE {{ WORK_ORDER_FILTER }}
)
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
WHERE (
    h.CONTAINERID IN (SELECT CONTAINERID FROM work_order_lots)
    OR h.FROMCONTAINERID IN (SELECT CONTAINERID FROM work_order_lots)
)
  AND h.FROMCONTAINERID IS NOT NULL
  {{ TIME_WINDOW }}
ORDER BY h.TXNDATE
{{ ROW_LIMIT }}
