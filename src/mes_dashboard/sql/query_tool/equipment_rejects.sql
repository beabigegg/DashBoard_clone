-- Equipment Reject Statistics
-- Aggregates reject statistics by equipment for a time period
--
-- Parameters:
--   :start_date - Start date (YYYY-MM-DD)
--   :end_date - End date (YYYY-MM-DD)
--
-- Dynamic placeholders:
--   EQUIPMENT_FILTER - Equipment filter condition (on EQUIPMENTNAME)
--
-- Note: LOTREJECTHISTORY only has EQUIPMENTNAME, NO EQUIPMENTID
--       If need to filter by EQUIPMENTID, must JOIN LOTWIPHISTORY
--       Uses LOSSREASONNAME (NOT REJECTREASONNAME)
--       Uses TXNDATE (NOT TXNDATETIME)

SELECT
    EQUIPMENTNAME,
    REJECTCATEGORYNAME,
    LOSSREASONNAME,
    SUM(REJECTQTY) AS TOTAL_REJECT_QTY,
    COUNT(DISTINCT CONTAINERID) AS AFFECTED_LOT_COUNT
FROM DWH.DW_MES_LOTREJECTHISTORY
WHERE TXNDATE >= TO_DATE(:start_date, 'YYYY-MM-DD')
  AND TXNDATE < TO_DATE(:end_date, 'YYYY-MM-DD') + 1
  AND {{ EQUIPMENT_FILTER }}
GROUP BY EQUIPMENTNAME, REJECTCATEGORYNAME, LOSSREASONNAME
ORDER BY EQUIPMENTNAME, TOTAL_REJECT_QTY DESC
