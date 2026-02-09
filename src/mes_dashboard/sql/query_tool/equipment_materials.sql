-- Equipment Materials Consumption Summary
-- Aggregates material consumption by equipment for a time period
--
-- Parameters:
--   :start_date - Start date (YYYY-MM-DD)
--   :end_date - End date (YYYY-MM-DD)
--
-- Dynamic placeholders:
--   EQUIPMENT_FILTER - Equipment filter condition (on EQUIPMENTNAME)
--
-- Note: Uses MATERIALPARTNAME (NOT MATERIALNAME)
--       Uses QTYCONSUMED (NOT CONSUMEQTY)
--       Uses TXNDATE (NOT TXNDATETIME)

SELECT
    EQUIPMENTNAME,
    MATERIALPARTNAME,
    SUM(QTYCONSUMED) AS TOTAL_CONSUMED,
    COUNT(DISTINCT CONTAINERID) AS LOT_COUNT
FROM DWH.DW_MES_LOTMATERIALSHISTORY
WHERE TXNDATE >= TO_DATE(:start_date, 'YYYY-MM-DD')
  AND TXNDATE < TO_DATE(:end_date, 'YYYY-MM-DD') + 1
  AND {{ EQUIPMENT_FILTER }}
GROUP BY EQUIPMENTNAME, MATERIALPARTNAME
ORDER BY EQUIPMENTNAME, TOTAL_CONSUMED DESC
