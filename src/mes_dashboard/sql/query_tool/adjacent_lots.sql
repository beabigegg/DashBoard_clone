-- Optimized: query_tool/adjacent_lots
-- Change: Added /*+ MATERIALIZE */ hint to ranked_lots CTE
--         Without this hint, Oracle may re-evaluate ranked_lots 4-5 times
--         (once each for target_lot, first_diff_before, first_diff_after, final SELECT)

WITH time_bounds AS (
    SELECT
        :target_trackin_time - INTERVAL '1' HOUR * :time_window_hours AS time_start,
        :target_trackin_time + INTERVAL '1' HOUR * :time_window_hours AS time_end
    FROM DUAL
),
raw_lots AS (
    SELECT
        h.CONTAINERID,
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
        c.FIRSTNAME AS WAFER_LOT_ID
    FROM DWH.DW_MES_LOTWIPHISTORY h
    LEFT JOIN DWH.DW_MES_CONTAINER c ON h.CONTAINERID = c.CONTAINERID
    CROSS JOIN time_bounds tb
    WHERE h.EQUIPMENTID = :equipment_id
      AND h.TRACKINTIMESTAMP BETWEEN tb.time_start AND tb.time_end
),
ranked_lots AS (
    SELECT /*+ MATERIALIZE */
        d.*,
        ROW_NUMBER() OVER (
            PARTITION BY d.EQUIPMENTID
            ORDER BY d.TRACKINTIMESTAMP
        ) AS rn
    FROM raw_lots d
),
target_lot AS (
    SELECT rn AS target_rn, PJ_TYPE AS target_pj_type
    FROM ranked_lots
    WHERE TRACKINTIMESTAMP = :target_trackin_time
),
first_diff_before AS (
    SELECT MAX(r.rn) AS rn
    FROM ranked_lots r
    CROSS JOIN target_lot t
    WHERE r.rn < t.target_rn
      AND (
          (r.PJ_TYPE IS NULL AND t.target_pj_type IS NOT NULL)
          OR (r.PJ_TYPE IS NOT NULL AND t.target_pj_type IS NULL)
          OR (r.PJ_TYPE != t.target_pj_type)
      )
),
first_diff_after AS (
    SELECT MIN(r.rn) AS rn
    FROM ranked_lots r
    CROSS JOIN target_lot t
    WHERE r.rn > t.target_rn
      AND (
          (r.PJ_TYPE IS NULL AND t.target_pj_type IS NOT NULL)
          OR (r.PJ_TYPE IS NOT NULL AND t.target_pj_type IS NULL)
          OR (r.PJ_TYPE != t.target_pj_type)
      )
)
SELECT
    r.CONTAINERID,
    r.EQUIPMENTID,
    r.EQUIPMENTNAME,
    r.SPECNAME,
    r.TRACKINTIMESTAMP,
    r.TRACKOUTTIMESTAMP,
    r.TRACKINQTY,
    r.TRACKOUTQTY,
    r.FINISHEDRUNCARD,
    r.PJ_WORKORDER,
    r.CONTAINERNAME,
    r.PJ_TYPE,
    r.PJ_BOP,
    r.WAFER_LOT_ID,
    r.rn - t.target_rn AS RELATIVE_POSITION
FROM ranked_lots r
CROSS JOIN target_lot t
CROSS JOIN first_diff_before b
CROSS JOIN first_diff_after a
WHERE r.rn >= LEAST(NVL(b.rn, t.target_rn - 3), t.target_rn - 3)
  AND r.rn <= GREATEST(NVL(a.rn, t.target_rn + 3), t.target_rn + 3)
ORDER BY r.rn
