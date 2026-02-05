-- Adjacent Lots Query (前後批查詢)
-- Finds lots processed before and after a target lot on same equipment with same spec
--
-- Parameters:
--   :equipment_id - Target equipment ID
--   :spec_name - Target spec name
--   :target_trackin_time - Target lot's TRACKINTIMESTAMP
--   :time_window_hours - Time window in hours (default 24)
--
-- Note: Uses ROW_NUMBER() to identify relative position
--       Limited to ±time_window_hours to control result set

WITH time_bounds AS (
    SELECT
        :target_trackin_time - INTERVAL '1' HOUR * :time_window_hours AS time_start,
        :target_trackin_time + INTERVAL '1' HOUR * :time_window_hours AS time_end
    FROM DUAL
),
ranked_lots AS (
    SELECT
        h.CONTAINERID,
        h.EQUIPMENTID,
        h.EQUIPMENTNAME,
        h.SPECNAME,
        h.PJ_TYPE,
        h.TRACKINTIMESTAMP,
        h.TRACKOUTTIMESTAMP,
        h.TRACKINQTY,
        h.TRACKOUTQTY,
        h.FINISHEDRUNCARD,
        h.PJ_WORKORDER,
        c.CONTAINERNAME,
        ROW_NUMBER() OVER (
            PARTITION BY h.EQUIPMENTID, h.SPECNAME
            ORDER BY h.TRACKINTIMESTAMP
        ) AS rn
    FROM DWH.DW_MES_LOTWIPHISTORY h
    LEFT JOIN DWH.DW_MES_CONTAINER c ON h.CONTAINERID = c.CONTAINERID
    CROSS JOIN time_bounds tb
    WHERE h.EQUIPMENTID = :equipment_id
      AND h.SPECNAME = :spec_name
      AND h.TRACKINTIMESTAMP BETWEEN tb.time_start AND tb.time_end
),
target_lot AS (
    SELECT rn AS target_rn
    FROM ranked_lots
    WHERE TRACKINTIMESTAMP = :target_trackin_time
)
SELECT
    r.CONTAINERID,
    r.EQUIPMENTID,
    r.EQUIPMENTNAME,
    r.SPECNAME,
    r.PJ_TYPE,
    r.TRACKINTIMESTAMP,
    r.TRACKOUTTIMESTAMP,
    r.TRACKINQTY,
    r.TRACKOUTQTY,
    r.FINISHEDRUNCARD,
    r.PJ_WORKORDER,
    r.CONTAINERNAME,
    r.rn - t.target_rn AS RELATIVE_POSITION
FROM ranked_lots r
CROSS JOIN target_lot t
WHERE r.rn BETWEEN (t.target_rn - 3) AND (t.target_rn + 3)
ORDER BY r.rn
