-- Adjacent Lots Query (前後批查詢)
-- Finds lots processed before and after a target lot on the same equipment
-- Searches until finding a different PJ_TYPE, with minimum 3 lots in each direction
--
-- Parameters:
--   :equipment_id - Target equipment ID
--   :target_trackin_time - Target lot's TRACKINTIMESTAMP
--   :time_window_hours - Time window in hours (default 24)
--
-- Output columns:
--   PJ_TYPE - Product type (from DW_MES_CONTAINER)
--   PJ_BOP - BOP code (from DW_MES_CONTAINER)
--   WAFER_LOT_ID - Wafer lot ID, mapped from FIRSTNAME (from DW_MES_CONTAINER)
--
-- Logic:
--   1. Only filter by EQUIPMENTID (no SPECNAME restriction)
--   2. Search forward/backward until finding a different PJ_TYPE
--   3. Minimum 3 lots in each direction (even if different PJ_TYPE found earlier)
--   4. Stop at first different PJ_TYPE if found beyond 3 lots
--
-- Note: Deduplicates multiple track-out records for same track-in (takes latest track-out)

WITH time_bounds AS (
    SELECT
        :target_trackin_time - INTERVAL '1' HOUR * :time_window_hours AS time_start,
        :target_trackin_time + INTERVAL '1' HOUR * :time_window_hours AS time_end
    FROM DUAL
),
-- Step 1: Get all records and deduplicate
-- Multiple track-out records for same track-in -> take the latest track-out time
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
        c.FIRSTNAME AS WAFER_LOT_ID,
        ROW_NUMBER() OVER (
            PARTITION BY h.CONTAINERID, h.EQUIPMENTID, h.TRACKINTIMESTAMP
            ORDER BY h.TRACKOUTTIMESTAMP DESC NULLS LAST
        ) AS dedup_rn
    FROM DWH.DW_MES_LOTWIPHISTORY h
    LEFT JOIN DWH.DW_MES_CONTAINER c ON h.CONTAINERID = c.CONTAINERID
    CROSS JOIN time_bounds tb
    WHERE h.EQUIPMENTID = :equipment_id
      AND h.TRACKINTIMESTAMP BETWEEN tb.time_start AND tb.time_end
),
-- Step 2: Keep only deduplicated records
deduped_lots AS (
    SELECT *
    FROM raw_lots
    WHERE dedup_rn = 1
),
-- Step 3: Rank by track-in time (partitioned by EQUIPMENTID only)
ranked_lots AS (
    SELECT
        d.*,
        ROW_NUMBER() OVER (
            PARTITION BY d.EQUIPMENTID
            ORDER BY d.TRACKINTIMESTAMP
        ) AS rn
    FROM deduped_lots d
),
-- Step 4: Find target lot position and PJ_TYPE
target_lot AS (
    SELECT rn AS target_rn, PJ_TYPE AS target_pj_type
    FROM ranked_lots
    WHERE TRACKINTIMESTAMP = :target_trackin_time
),
-- Step 5: Find first lot BEFORE target with different PJ_TYPE
-- (highest rn that is less than target_rn and has different PJ_TYPE)
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
-- Step 6: Find first lot AFTER target with different PJ_TYPE
-- (lowest rn that is greater than target_rn and has different PJ_TYPE)
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
-- Step 7: Select lots within calculated range
-- Before: MIN(first_diff_before, target - 3) to ensure minimum 3 and stop at different PJ_TYPE
-- After: MAX(first_diff_after, target + 3) to ensure minimum 3 and stop at different PJ_TYPE
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
