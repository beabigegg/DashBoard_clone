-- Equipment Lots List Query
-- Retrieves all lots processed by equipment in a time period
--
-- Parameters:
--   :start_date - Start date (YYYY-MM-DD)
--   :end_date - End date (YYYY-MM-DD)
--
-- Dynamic placeholders:
--   EQUIPMENT_FILTER - Equipment filter condition (on EQUIPMENTID)
--
-- Note: Uses EQUIPMENTID/EQUIPMENTNAME (NOT RESOURCEID/RESOURCENAME)
--       JOIN CONTAINER to get CONTAINERNAME (LOT ID)

SELECT
    h.CONTAINERID,
    c.CONTAINERNAME,
    h.EQUIPMENTID,
    h.EQUIPMENTNAME,
    h.FINISHEDRUNCARD,
    h.SPECNAME,
    h.TRACKINTIMESTAMP,
    h.TRACKOUTTIMESTAMP,
    h.TRACKINQTY,
    h.TRACKOUTQTY,
    h.PJ_WORKORDER
FROM DWH.DW_MES_LOTWIPHISTORY h
LEFT JOIN DWH.DW_MES_CONTAINER c ON h.CONTAINERID = c.CONTAINERID
WHERE h.TRACKINTIMESTAMP >= TO_DATE(:start_date, 'YYYY-MM-DD')
  AND h.TRACKINTIMESTAMP < TO_DATE(:end_date, 'YYYY-MM-DD') + 1
  AND {{ EQUIPMENT_FILTER }}
ORDER BY h.EQUIPMENTNAME, h.TRACKINTIMESTAMP
