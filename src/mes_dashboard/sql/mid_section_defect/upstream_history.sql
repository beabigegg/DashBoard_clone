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
        CASE
            WHEN UPPER(h.WORKCENTERNAME) LIKE '%元件切割%'
                OR UPPER(h.WORKCENTERNAME) LIKE '%PKG_SAW%' THEN '元件切割'
            WHEN UPPER(h.WORKCENTERNAME) LIKE '%切割%' THEN '切割'
            WHEN UPPER(h.WORKCENTERNAME) LIKE '%焊接_DB%'
                OR UPPER(h.WORKCENTERNAME) LIKE '%焊_DB_料%'
                OR UPPER(h.WORKCENTERNAME) LIKE '%焊_DB%' THEN '焊接_DB'
            WHEN UPPER(h.WORKCENTERNAME) LIKE '%焊接_WB%'
                OR UPPER(h.WORKCENTERNAME) LIKE '%焊_WB_料%'
                OR UPPER(h.WORKCENTERNAME) LIKE '%焊_WB%' THEN '焊接_WB'
            WHEN UPPER(h.WORKCENTERNAME) LIKE '%焊接_DW%'
                OR UPPER(h.WORKCENTERNAME) LIKE '%焊_DW%'
                OR UPPER(h.WORKCENTERNAME) LIKE '%焊_DW_料%' THEN '焊接_DW'
            WHEN UPPER(h.WORKCENTERNAME) LIKE '%成型%'
                OR UPPER(h.WORKCENTERNAME) LIKE '%成型_料%' THEN '成型'
            WHEN UPPER(h.WORKCENTERNAME) LIKE '%去膠%' THEN '去膠'
            WHEN UPPER(h.WORKCENTERNAME) LIKE '%水吹砂%' THEN '水吹砂'
            WHEN UPPER(h.WORKCENTERNAME) LIKE '%掛鍍%'
                OR UPPER(h.WORKCENTERNAME) LIKE '%滾鍍%'
                OR UPPER(h.WORKCENTERNAME) LIKE '%條鍍%'
                OR UPPER(h.WORKCENTERNAME) LIKE '%電鍍%'
                OR UPPER(h.WORKCENTERNAME) LIKE '%補鍍%'
                OR UPPER(h.WORKCENTERNAME) LIKE '%TOTAI%'
                OR UPPER(h.WORKCENTERNAME) LIKE '%BANDL%' THEN '電鍍'
            WHEN UPPER(h.WORKCENTERNAME) LIKE '%移印%' THEN '移印'
            WHEN UPPER(h.WORKCENTERNAME) LIKE '%切彎腳%' THEN '切彎腳'
            WHEN UPPER(h.WORKCENTERNAME) LIKE '%TMTT%'
                OR UPPER(h.WORKCENTERNAME) LIKE '%測試%' THEN '測試'
            ELSE NULL
        END AS WORKCENTER_GROUP,
        h.EQUIPMENTID,
        h.EQUIPMENTNAME,
        h.SPECNAME,
        h.TRACKINTIMESTAMP,
        NVL(h.TRACKINQTY, 0) AS TRACKINQTY,
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
    WORKCENTER_GROUP,
    EQUIPMENTID,
    EQUIPMENTNAME,
    SPECNAME,
    TRACKINTIMESTAMP,
    TRACKINQTY
FROM ranked_history
WHERE rn = 1
ORDER BY CONTAINERID, TRACKINTIMESTAMP
