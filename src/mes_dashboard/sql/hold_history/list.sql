-- Optimized: hold_history/list
-- Changes:
--   1. Added HOLDTXNDATE WHERE to history_base CTE to enable index scan
--   2. Computed hold_hours ONCE in history_base, referenced in filtered
--      (was: 4× redundant CASE recalculation in WHERE clause)

WITH history_base AS (
  SELECT
    CASE
      WHEN TO_CHAR(h.HOLDTXNDATE, 'HH24MI') >= '0730' THEN TRUNC(h.HOLDTXNDATE) + 1
      ELSE TRUNC(h.HOLDTXNDATE)
    END AS hold_day,
    h.CONTAINERID,
    h.PJ_WORKORDER,
    h.WORKCENTERNAME,
    h.HOLDREASONNAME,
    h.HOLDTXNDATE,
    NVL(h.QTY, 0) AS QTY,
    h.HOLDEMP,
    h.HOLDCOMMENTS,
    h.RELEASETXNDATE,
    h.RELEASEEMP,
    h.RELEASECOMMENTS,
    h.NCRID,
    h.FUTUREHOLDCOMMENTS,
    CASE
      WHEN h.HOLDREASONNAME IN ({{ NON_QUALITY_REASONS }}) THEN 'non-quality'
      ELSE 'quality'
    END AS hold_type,
    CASE
      WHEN h.RELEASETXNDATE IS NULL THEN (SYSDATE - h.HOLDTXNDATE) * 24
      ELSE (h.RELEASETXNDATE - h.HOLDTXNDATE) * 24
    END AS hold_hours
  FROM DWH.DW_MES_HOLDRELEASEHISTORY h
  WHERE h.HOLDTXNDATE >= TO_DATE(:start_date, 'YYYY-MM-DD') - 1
    AND h.HOLDTXNDATE <= TO_DATE(:end_date, 'YYYY-MM-DD') + 1
),
filtered AS (
  SELECT b.*
  FROM history_base b
  WHERE b.hold_day BETWEEN TO_DATE(:start_date, 'YYYY-MM-DD') AND TO_DATE(:end_date, 'YYYY-MM-DD')
    AND (:hold_type = 'all' OR b.hold_type = :hold_type)
    AND (:reason IS NULL OR b.HOLDREASONNAME = :reason)
    AND (:include_new = 1
      OR (:include_on_hold = 1 AND b.RELEASETXNDATE IS NULL)
      OR (:include_released = 1 AND b.RELEASETXNDATE IS NOT NULL))
    AND (:duration_range IS NULL
      OR (:duration_range = '<4h'  AND b.hold_hours < 4)
      OR (:duration_range = '4-24h' AND b.hold_hours >= 4 AND b.hold_hours < 24)
      OR (:duration_range = '1-3d' AND b.hold_hours >= 24 AND b.hold_hours < 72)
      OR (:duration_range = '>3d'  AND b.hold_hours >= 72))
),
ranked AS (
  SELECT
    NVL(c.CONTAINERNAME, TRIM(f.CONTAINERID)) AS lot_id,
    f.PJ_WORKORDER AS workorder,
    c.PRODUCTNAME AS product,
    f.WORKCENTERNAME AS workcenter,
    f.HOLDREASONNAME AS hold_reason,
    f.QTY AS qty,
    f.HOLDTXNDATE AS hold_date,
    f.HOLDEMP AS hold_emp,
    f.HOLDCOMMENTS AS hold_comment,
    f.RELEASETXNDATE AS release_date,
    f.RELEASEEMP AS release_emp,
    f.RELEASECOMMENTS AS release_comment,
    f.hold_hours,
    f.NCRID AS ncr_id,
    f.FUTUREHOLDCOMMENTS AS future_hold_comment,
    TRIM(c.PRODUCTLINENAME) AS package,
    ROW_NUMBER() OVER (ORDER BY f.HOLDTXNDATE DESC, f.CONTAINERID) AS rn,
    COUNT(*) OVER () AS total_count
  FROM filtered f
  LEFT JOIN DWH.DW_MES_CONTAINER c ON c.CONTAINERID = f.CONTAINERID
)
SELECT
  lot_id,
  workorder,
  product,
  workcenter,
  hold_reason,
  qty,
  hold_date,
  hold_emp,
  hold_comment,
  release_date,
  release_emp,
  release_comment,
  hold_hours,
  ncr_id,
  future_hold_comment,
  package,
  total_count
FROM ranked
WHERE rn > :offset
  AND rn <= :offset + :limit
ORDER BY rn
