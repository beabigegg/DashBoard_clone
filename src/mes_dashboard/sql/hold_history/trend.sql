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
)
SELECT
  TO_CHAR(c.day_date, 'YYYY-MM-DD') AS txn_date,
  t.hold_type,
  SUM(
    CASE
      WHEN (t.hold_type = 'all' OR h.hold_type = t.hold_type)
        AND h.hold_day <= c.day_date
        AND (h.release_day IS NULL OR c.day_date < h.release_day)
        AND c.day_date <= TRUNC(SYSDATE)
        AND h.rn_hold_day = 1
      THEN h.qty
      ELSE 0
    END
  ) AS hold_qty,
  SUM(
    CASE
      WHEN (t.hold_type = 'all' OR h.hold_type = t.hold_type)
        AND h.hold_day = c.day_date
        AND (h.release_day IS NULL OR c.day_date <= h.release_day)
        AND h.future_hold_flag = 1
      THEN h.qty
      ELSE 0
    END
  ) AS new_hold_qty,
  SUM(
    CASE
      WHEN (t.hold_type = 'all' OR h.hold_type = t.hold_type)
        AND h.release_day = c.day_date
        AND h.release_day >= h.hold_day
      THEN h.qty
      ELSE 0
    END
  ) AS release_qty,
  SUM(
    CASE
      WHEN (t.hold_type = 'all' OR h.hold_type = t.hold_type)
        AND h.hold_day = c.day_date
        AND (h.release_day IS NULL OR c.day_date <= h.release_day)
        AND h.rn_hold_day = 1
        AND h.future_hold_flag = 0
      THEN h.qty
      ELSE 0
    END
  ) AS future_hold_qty
FROM calendar c
CROSS JOIN hold_types t
LEFT JOIN history_enriched h ON 1 = 1
GROUP BY c.day_date, t.hold_type
ORDER BY c.day_date, t.hold_type
