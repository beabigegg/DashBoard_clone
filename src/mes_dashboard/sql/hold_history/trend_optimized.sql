-- Optimized: hold_history/trend
-- Changes:
--   1. Replaced LEFT JOIN ... ON 1=1 (Cartesian) with proper date-range overlap join
--   2. Added HOLDTXNDATE WHERE clause to history_base to enable index scan
--   3. Pre-aggregate daily metrics per hold_type before joining to calendar

WITH calendar AS (
  SELECT TRUNC(TO_DATE(:start_date, 'YYYY-MM-DD')) + LEVEL - 1 AS day_date
  FROM dual
  CONNECT BY LEVEL <= (
    TRUNC(TO_DATE(:end_date, 'YYYY-MM-DD')) - TRUNC(TO_DATE(:start_date, 'YYYY-MM-DD')) + 1
  )
),
hold_types AS (
  SELECT 'quality' AS hold_type FROM dual
  UNION ALL
  SELECT 'non-quality' AS hold_type FROM dual
  UNION ALL
  SELECT 'all' AS hold_type FROM dual
),
history_base AS (
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
    h.HOLDTXNDATE,
    h.RELEASETXNDATE,
    h.CONTAINERID,
    NVL(h.QTY, 0) AS qty,
    h.HOLDREASONID,
    h.HOLDREASONNAME,
    CASE
      WHEN h.FUTUREHOLDCOMMENTS IS NOT NULL THEN 1
      ELSE 0
    END AS is_future_hold,
    ROW_NUMBER() OVER (
      PARTITION BY
        h.CONTAINERID,
        CASE
          WHEN TO_CHAR(h.HOLDTXNDATE, 'HH24MI') >= '0730' THEN TRUNC(h.HOLDTXNDATE) + 1
          ELSE TRUNC(h.HOLDTXNDATE)
        END
      ORDER BY h.HOLDTXNDATE DESC
    ) AS rn_hold_day,
    ROW_NUMBER() OVER (
      PARTITION BY h.CONTAINERID, h.HOLDREASONID
      ORDER BY h.HOLDTXNDATE
    ) AS rn_future_reason
  FROM DWH.DW_MES_HOLDRELEASEHISTORY h
  WHERE (
      h.HOLDTXNDATE >= TO_DATE(:start_date || ' 073000', 'YYYY-MM-DD HH24MISS') - 1
      OR h.RELEASETXNDATE >= TO_DATE(:start_date || ' 073000', 'YYYY-MM-DD HH24MISS') - 1
      OR h.RELEASETXNDATE IS NULL
    )
    AND (
      h.HOLDTXNDATE <= TO_DATE(:end_date || ' 073000', 'YYYY-MM-DD HH24MISS')
      OR h.RELEASETXNDATE <= TO_DATE(:end_date || ' 073000', 'YYYY-MM-DD HH24MISS')
      OR h.RELEASETXNDATE IS NULL
    )
),
history_enriched AS (
  SELECT
    hold_day,
    release_day,
    HOLDTXNDATE,
    RELEASETXNDATE,
    CONTAINERID,
    qty,
    HOLDREASONID,
    HOLDREASONNAME,
    rn_hold_day,
    CASE
      WHEN is_future_hold = 1 AND rn_future_reason <> 1 THEN 0
      ELSE 1
    END AS future_hold_flag,
    CASE
      WHEN HOLDREASONNAME IN ({{ NON_QUALITY_REASONS }}) THEN 'non-quality'
      ELSE 'quality'
    END AS hold_type
  FROM history_base
),
-- Pre-aggregate: hold_qty per (day, hold_type) — snapshot of lots on hold at each day
daily_hold AS (
  SELECT
    c.day_date,
    h.hold_type,
    SUM(CASE
      WHEN h.hold_day <= c.day_date
        AND (h.release_day IS NULL OR c.day_date < h.release_day)
        AND c.day_date <= TRUNC(SYSDATE)
        AND h.rn_hold_day = 1
      THEN h.qty ELSE 0
    END) AS hold_qty,
    SUM(CASE
      WHEN h.hold_day = c.day_date
        AND (h.release_day IS NULL OR c.day_date <= h.release_day)
        AND h.future_hold_flag = 1
      THEN h.qty ELSE 0
    END) AS new_hold_qty,
    SUM(CASE
      WHEN h.release_day = c.day_date
        AND h.release_day >= h.hold_day
      THEN h.qty ELSE 0
    END) AS release_qty,
    SUM(CASE
      WHEN h.hold_day = c.day_date
        AND (h.release_day IS NULL OR c.day_date <= h.release_day)
        AND h.rn_hold_day = 1
        AND h.future_hold_flag = 0
      THEN h.qty ELSE 0
    END) AS future_hold_qty
  FROM calendar c
  JOIN history_enriched h
    ON h.hold_day <= c.day_date + 1
    AND (h.release_day IS NULL OR h.release_day >= c.day_date)
  GROUP BY c.day_date, h.hold_type
),
-- Combine with 'all' hold_type (sum of quality + non-quality)
daily_all AS (
  SELECT
    day_date,
    'all' AS hold_type,
    SUM(hold_qty) AS hold_qty,
    SUM(new_hold_qty) AS new_hold_qty,
    SUM(release_qty) AS release_qty,
    SUM(future_hold_qty) AS future_hold_qty
  FROM daily_hold
  GROUP BY day_date
)
SELECT
  TO_CHAR(c.day_date, 'YYYY-MM-DD') AS txn_date,
  t.hold_type,
  NVL(d.hold_qty, 0) AS hold_qty,
  NVL(d.new_hold_qty, 0) AS new_hold_qty,
  NVL(d.release_qty, 0) AS release_qty,
  NVL(d.future_hold_qty, 0) AS future_hold_qty
FROM calendar c
CROSS JOIN hold_types t
LEFT JOIN (
  SELECT day_date, hold_type, hold_qty, new_hold_qty, release_qty, future_hold_qty
  FROM daily_hold
  UNION ALL
  SELECT day_date, hold_type, hold_qty, new_hold_qty, release_qty, future_hold_qty
  FROM daily_all
) d ON d.day_date = c.day_date AND d.hold_type = t.hold_type
ORDER BY c.day_date, t.hold_type
