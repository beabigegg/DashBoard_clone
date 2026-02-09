-- LOT Production History Query
-- Retrieves complete production history for a LOT
--
-- Parameters:
--   :container_id - CONTAINERID to query (16-char hex)
--   {{ WORKCENTER_FILTER }} - Optional workcenter name filter (replaced by service)
--
-- Output columns:
--   PJ_TYPE - Product type (from DW_MES_CONTAINER)
--   PJ_BOP - BOP code (from DW_MES_CONTAINER)
--   WAFER_LOT_ID - Wafer lot ID, mapped from FIRSTNAME (from DW_MES_CONTAINER)
--
-- Note: Uses EQUIPMENTID/EQUIPMENTNAME (NOT RESOURCEID/RESOURCENAME)
--       Time fields: TRACKINTIMESTAMP/TRACKOUTTIMESTAMP (NOT TXNDATETIME)
--       Partial track-out: Same LOT may have multiple records with same track-in
--       but different track-out times. We take the latest track-out time.
--       Only includes records with actual equipment (excludes checkpoint stations)

WITH ranked_history AS (
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
    WHERE h.CONTAINERID = :container_id
      AND h.EQUIPMENTID IS NOT NULL
      AND h.TRACKINTIMESTAMP IS NOT NULL
      {{ WORKCENTER_FILTER }}
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
FROM ranked_history
WHERE rn = 1
ORDER BY TRACKINTIMESTAMP
