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
    CASE
      WHEN h.HOLDREASONNAME IN ({{ NON_QUALITY_REASONS }}) THEN 'non-quality'
      ELSE 'quality'
    END AS hold_type
  FROM DWH.DW_MES_HOLDRELEASEHISTORY h
),
filtered AS (
  SELECT
    b.*,
    CASE
      WHEN b.RELEASETXNDATE IS NULL THEN (SYSDATE - b.HOLDTXNDATE) * 24
      ELSE (b.RELEASETXNDATE - b.HOLDTXNDATE) * 24
    END AS hold_hours
  FROM history_base b
  WHERE b.hold_day BETWEEN TO_DATE(:start_date, 'YYYY-MM-DD') AND TO_DATE(:end_date, 'YYYY-MM-DD')
    AND (:hold_type = 'all' OR b.hold_type = :hold_type)
    AND (:reason IS NULL OR b.HOLDREASONNAME = :reason)
    AND (:include_new = 1
      OR (:include_on_hold = 1 AND b.RELEASETXNDATE IS NULL)
      OR (:include_released = 1 AND b.RELEASETXNDATE IS NOT NULL))
    AND (:duration_range IS NULL
      OR (:duration_range = '<4h' AND
          CASE WHEN b.RELEASETXNDATE IS NULL THEN (SYSDATE - b.HOLDTXNDATE) * 24
               ELSE (b.RELEASETXNDATE - b.HOLDTXNDATE) * 24 END < 4)
      OR (:duration_range = '4-24h' AND
          CASE WHEN b.RELEASETXNDATE IS NULL THEN (SYSDATE - b.HOLDTXNDATE) * 24
               ELSE (b.RELEASETXNDATE - b.HOLDTXNDATE) * 24 END >= 4 AND
          CASE WHEN b.RELEASETXNDATE IS NULL THEN (SYSDATE - b.HOLDTXNDATE) * 24
               ELSE (b.RELEASETXNDATE - b.HOLDTXNDATE) * 24 END < 24)
      OR (:duration_range = '1-3d' AND
          CASE WHEN b.RELEASETXNDATE IS NULL THEN (SYSDATE - b.HOLDTXNDATE) * 24
               ELSE (b.RELEASETXNDATE - b.HOLDTXNDATE) * 24 END >= 24 AND
          CASE WHEN b.RELEASETXNDATE IS NULL THEN (SYSDATE - b.HOLDTXNDATE) * 24
               ELSE (b.RELEASETXNDATE - b.HOLDTXNDATE) * 24 END < 72)
      OR (:duration_range = '>3d' AND
          CASE WHEN b.RELEASETXNDATE IS NULL THEN (SYSDATE - b.HOLDTXNDATE) * 24
               ELSE (b.RELEASETXNDATE - b.HOLDTXNDATE) * 24 END >= 72))
),
ranked AS (
  SELECT
    NVL(l.LOTID, TRIM(f.CONTAINERID)) AS lot_id,
    f.PJ_WORKORDER AS workorder,
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
    ROW_NUMBER() OVER (ORDER BY f.HOLDTXNDATE DESC, f.CONTAINERID) AS rn,
    COUNT(*) OVER () AS total_count
  FROM filtered f
  LEFT JOIN DWH.DW_MES_LOT_V l ON l.CONTAINERID = f.CONTAINERID
)
SELECT
  lot_id,
  workorder,
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
  total_count
FROM ranked
WHERE rn > :offset
  AND rn <= :offset + :limit
ORDER BY rn
