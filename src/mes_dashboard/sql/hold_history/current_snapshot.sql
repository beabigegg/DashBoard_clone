/*
 * Current-snapshot query — 現況 mode.
 *
 * Shows the real-time live state: all currently unreleased lots, plus
 * new holds and releases since the start of the current shift.
 *
 * Shift naming: START-day convention.
 *   >= 07:30 → shift_day = TRUNC(date)       (shift started today)
 *   <  07:30 → shift_day = TRUNC(date) - 1   (shift started yesterday)
 *
 * today_date = shift_start (computed from SYSDATE with START-day logic).
 *
 * HOLD_HOURS for unreleased lots uses SYSDATE (true live duration).
 */
WITH current_shift AS (
  SELECT
    CASE
      WHEN TO_CHAR(SYSDATE, 'HH24MI') >= '0730' THEN TRUNC(SYSDATE)
      ELSE TRUNC(SYSDATE) - 1
    END AS shift_start
  FROM DUAL
),
facts AS (
  SELECT
    CASE
      WHEN TO_CHAR(h.HOLDTXNDATE, 'HH24MI') >= '0730' THEN TRUNC(h.HOLDTXNDATE)
      ELSE TRUNC(h.HOLDTXNDATE) - 1
    END AS hold_day,
    CASE
      WHEN h.RELEASETXNDATE IS NULL THEN NULL
      WHEN TO_CHAR(h.RELEASETXNDATE, 'HH24MI') >= '0730' THEN TRUNC(h.RELEASETXNDATE)
      ELSE TRUNC(h.RELEASETXNDATE) - 1
    END AS release_day,
    h.CONTAINERID,
    NVL(TRIM(c.CONTAINERNAME), TRIM(h.CONTAINERID)) AS LOT_ID,
    h.PJ_WORKORDER,
    c.PRODUCTNAME,
    h.WORKCENTERNAME,
    h.HOLDREASONID,
    h.HOLDREASONNAME,
    NVL(h.QTY, 0) AS QTY,
    h.HOLDTXNDATE,
    h.HOLDEMP,
    h.HOLDCOMMENTS,
    h.RELEASETXNDATE,
    h.RELEASEEMP,
    h.RELEASECOMMENTS,
    h.NCRID,
    h.FUTUREHOLDCOMMENTS,
    CASE
      WHEN h.RELEASETXNDATE IS NULL THEN (SYSDATE - h.HOLDTXNDATE) * 24
      ELSE (h.RELEASETXNDATE - h.HOLDTXNDATE) * 24
    END AS HOLD_HOURS,
    CASE
      WHEN h.HOLDREASONNAME IN ({{ NON_QUALITY_REASONS }}) THEN 'non-quality'
      ELSE 'quality'
    END AS HOLD_TYPE,
    CASE
      WHEN h.FUTUREHOLDCOMMENTS IS NOT NULL THEN 1
      ELSE 0
    END AS IS_FUTURE_HOLD,
    ROW_NUMBER() OVER (
      PARTITION BY h.CONTAINERID, h.HOLDREASONID
      ORDER BY h.HOLDTXNDATE
    ) AS RN_FUTURE_REASON,
    s.shift_start AS today_date
  FROM DWH.DW_MES_HOLDRELEASEHISTORY h
  LEFT JOIN DWH.DW_MES_CONTAINER c ON c.CONTAINERID = h.CONTAINERID
  CROSS JOIN current_shift s
  WHERE
    h.RELEASETXNDATE IS NULL
    OR CASE
         WHEN TO_CHAR(h.RELEASETXNDATE, 'HH24MI') >= '0730' THEN TRUNC(h.RELEASETXNDATE)
         ELSE TRUNC(h.RELEASETXNDATE) - 1
       END = s.shift_start
    OR CASE
         WHEN TO_CHAR(h.HOLDTXNDATE, 'HH24MI') >= '0730' THEN TRUNC(h.HOLDTXNDATE)
         ELSE TRUNC(h.HOLDTXNDATE) - 1
       END = s.shift_start
)
SELECT
  hold_day,
  release_day,
  today_date,
  CONTAINERID,
  LOT_ID,
  PJ_WORKORDER,
  PRODUCTNAME,
  WORKCENTERNAME,
  HOLDREASONID,
  HOLDREASONNAME,
  QTY,
  HOLDTXNDATE,
  HOLDEMP,
  HOLDCOMMENTS,
  RELEASETXNDATE,
  RELEASEEMP,
  RELEASECOMMENTS,
  NCRID,
  FUTUREHOLDCOMMENTS,
  HOLD_HOURS,
  HOLD_TYPE,
  IS_FUTURE_HOLD,
  RN_FUTURE_REASON,
  CASE
    WHEN IS_FUTURE_HOLD = 1 AND RN_FUTURE_REASON <> 1 THEN 0
    ELSE 1
  END AS FUTURE_HOLD_FLAG
FROM facts
FETCH FIRST :max_rows ROWS ONLY
