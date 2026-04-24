/*
 * Today-snapshot query — 當日 mode.
 *
 * "當日 4/24" = the shift labeled by today's calendar date, using END-day convention
 * (same as base_facts.sql): shift that ENDS at 07:30 today.
 *   >= 07:30 → shift_day = TRUNC(date) + 1
 *   <  07:30 → shift_day = TRUNC(date)
 *
 * today_date = TRUNC(SYSDATE) — calendar date; no time adjustment.
 *
 * HOLD_HOURS for unreleased lots uses LEAST(SYSDATE, today 07:30) so that
 * after the shift closes, hours are frozen at the shift boundary.
 *
 * WHERE includes four cases:
 *   1. Currently unreleased (RELEASETXNDATE IS NULL)
 *   2. Released during today's shift (release_day = today)
 *   3. Put on hold during today's shift (hold_day = today)
 *   4. Was on hold at shift boundary, released after (hold_day < today AND release_day > today)
 */
WITH today_date AS (
  SELECT TRUNC(SYSDATE) AS today
  FROM DUAL
),
facts AS (
  SELECT
    CASE
      WHEN TO_CHAR(h.HOLDTXNDATE, 'HH24MI') >= '0730' THEN TRUNC(h.HOLDTXNDATE) + 1
      ELSE TRUNC(h.HOLDTXNDATE)
    END AS hold_day,
    CASE
      WHEN h.RELEASETXNDATE IS NULL THEN NULL
      WHEN TO_CHAR(h.RELEASETXNDATE, 'HH24MI') >= '0730' THEN TRUNC(h.RELEASETXNDATE) + 1
      ELSE TRUNC(h.RELEASETXNDATE)
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
      WHEN h.RELEASETXNDATE IS NULL THEN
        (LEAST(SYSDATE, TRUNC(SYSDATE) + 7.5/24) - h.HOLDTXNDATE) * 24
      ELSE
        (h.RELEASETXNDATE - h.HOLDTXNDATE) * 24
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
    t.today AS today_date
  FROM DWH.DW_MES_HOLDRELEASEHISTORY h
  LEFT JOIN DWH.DW_MES_CONTAINER c ON c.CONTAINERID = h.CONTAINERID
  CROSS JOIN today_date t
  WHERE
    h.RELEASETXNDATE IS NULL
    OR CASE
         WHEN TO_CHAR(h.RELEASETXNDATE, 'HH24MI') >= '0730' THEN TRUNC(h.RELEASETXNDATE) + 1
         ELSE TRUNC(h.RELEASETXNDATE)
       END = t.today
    OR CASE
         WHEN TO_CHAR(h.HOLDTXNDATE, 'HH24MI') >= '0730' THEN TRUNC(h.HOLDTXNDATE) + 1
         ELSE TRUNC(h.HOLDTXNDATE)
       END = t.today
    OR (
      CASE
        WHEN TO_CHAR(h.HOLDTXNDATE, 'HH24MI') >= '0730' THEN TRUNC(h.HOLDTXNDATE) + 1
        ELSE TRUNC(h.HOLDTXNDATE)
      END < t.today
      AND CASE
        WHEN TO_CHAR(h.RELEASETXNDATE, 'HH24MI') >= '0730' THEN TRUNC(h.RELEASETXNDATE) + 1
        ELSE TRUNC(h.RELEASETXNDATE)
      END > t.today
    )
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
