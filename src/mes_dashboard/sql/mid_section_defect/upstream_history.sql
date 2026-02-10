-- Mid-Section Defect Traceability - Upstream Production History (Query 3)
-- Get production history for ancestor LOTs at all stations
--
-- Parameters:
--   Dynamically built IN clause for ancestor CONTAINERIDs
--
-- Tables used:
--   DWH.DW_MES_LOTWIPHISTORY (53M rows, CONTAINERID indexed → fast)
--
-- Performance:
--   CONTAINERID has index. Batch IN clause (up to 1000 per query).
--   Estimated 1-5s per batch.
--
WITH ranked_history AS (
    SELECT
        h.CONTAINERID,
        h.WORKCENTERNAME,
        h.EQUIPMENTID,
        h.EQUIPMENTNAME,
        h.SPECNAME,
        h.TRACKINTIMESTAMP,
        ROW_NUMBER() OVER (
            PARTITION BY h.CONTAINERID, h.WORKCENTERNAME, h.EQUIPMENTNAME
            ORDER BY h.TRACKINTIMESTAMP DESC
        ) AS rn
    FROM DWH.DW_MES_LOTWIPHISTORY h
    WHERE {{ ANCESTOR_FILTER }}
      AND h.EQUIPMENTID IS NOT NULL
      AND h.TRACKINTIMESTAMP IS NOT NULL
)
SELECT
    CONTAINERID,
    WORKCENTERNAME,
    EQUIPMENTID,
    EQUIPMENTNAME,
    SPECNAME,
    TRACKINTIMESTAMP
FROM ranked_history
WHERE rn = 1
ORDER BY CONTAINERID, TRACKINTIMESTAMP
