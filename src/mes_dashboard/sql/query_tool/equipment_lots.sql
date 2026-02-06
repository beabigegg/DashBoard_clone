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
--       JOIN CONTAINER to get CONTAINERNAME, PJ_TYPE, PJ_BOP, WAFER_LOT_ID
--       Partial track-out: Same LOT may have multiple records with same track-in
--       but different track-out times. We take the latest track-out time.
--       Only includes records with actual equipment (excludes checkpoint stations)

WITH ranked_lots AS (
    SELECT
        h.CONTAINERID,
        h.WORKCENTERNAME,
        h.EQUIPMENTID,
        h.EQUIPMENTNAME,
        h.SPECNAME,
        h.TRACKINTIMESTAMP,
        h.TRACKOUTTIMESTAMP,
        h.TRACKINQTY,
        h.TRACKOUTQTY,
        h.FINISHEDRUNCARD,
        h.PJ_WORKORDER,
        c.CONTAINERNAME,
        c.PJ_TYPE,
        c.PJ_BOP,
        c.FIRSTNAME AS WAFER_LOT_ID,
        ROW_NUMBER() OVER (
            PARTITION BY h.CONTAINERID, h.EQUIPMENTID, h.SPECNAME, h.TRACKINTIMESTAMP
            ORDER BY h.TRACKOUTTIMESTAMP DESC NULLS LAST
        ) AS rn
    FROM DWH.DW_MES_LOTWIPHISTORY h
    LEFT JOIN DWH.DW_MES_CONTAINER c ON h.CONTAINERID = c.CONTAINERID
    WHERE h.TRACKINTIMESTAMP >= TO_DATE(:start_date, 'YYYY-MM-DD')
      AND h.TRACKINTIMESTAMP < TO_DATE(:end_date, 'YYYY-MM-DD') + 1
      AND h.EQUIPMENTID IS NOT NULL
      AND h.TRACKINTIMESTAMP IS NOT NULL
      AND {{ EQUIPMENT_FILTER }}
)
SELECT
    CONTAINERID,
    WORKCENTERNAME,
    EQUIPMENTID,
    EQUIPMENTNAME,
    SPECNAME,
    TRACKINTIMESTAMP,
    TRACKOUTTIMESTAMP,
    TRACKINQTY,
    TRACKOUTQTY,
    FINISHEDRUNCARD,
    PJ_WORKORDER,
    CONTAINERNAME,
    PJ_TYPE,
    PJ_BOP,
    WAFER_LOT_ID
FROM ranked_lots
WHERE rn = 1
ORDER BY EQUIPMENTNAME, TRACKINTIMESTAMP
