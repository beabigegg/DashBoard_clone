-- Optimized: hold_history/duration
-- Change: Added HOLDTXNDATE WHERE to history_base CTE to enable index scan
--         (±1 day buffer accounts for 07:30 shift boundary)

WITH history_base AS (
  SELECT
    CASE
      WHEN TO_CHAR(h.HOLDTXNDATE, 'HH24MI') >= '0730' THEN TRUNC(h.HOLDTXNDATE) + 1
      ELSE TRUNC(h.HOLDTXNDATE)
    END AS hold_day,
    h.HOLDTXNDATE,
    h.RELEASETXNDATE,
    NVL(h.QTY, 0) AS qty,
    CASE
      WHEN h.HOLDREASONNAME IN ({{ NON_QUALITY_REASONS }}) THEN 'non-quality'
      ELSE 'quality'
    END AS hold_type
  FROM DWH.DW_MES_HOLDRELEASEHISTORY h
  WHERE h.HOLDTXNDATE >= TO_DATE(:start_date, 'YYYY-MM-DD') - 1
    AND h.HOLDTXNDATE <= TO_DATE(:end_date, 'YYYY-MM-DD') + 1
),
filtered AS (
  SELECT
    CASE
      WHEN RELEASETXNDATE IS NULL THEN (SYSDATE - HOLDTXNDATE) * 24
      ELSE (RELEASETXNDATE - HOLDTXNDATE) * 24
    END AS hold_hours,
    qty,
    CASE WHEN RELEASETXNDATE IS NOT NULL THEN 1 ELSE 0 END AS is_released
  FROM history_base
  WHERE hold_day BETWEEN TO_DATE(:start_date, 'YYYY-MM-DD') AND TO_DATE(:end_date, 'YYYY-MM-DD')
    AND (:hold_type = 'all' OR hold_type = :hold_type)
    AND (:include_new = 1
      OR (:include_on_hold = 1 AND RELEASETXNDATE IS NULL)
      OR (:include_released = 1 AND RELEASETXNDATE IS NOT NULL))
),
released_agg AS (
  SELECT
    ROUND(AVG(hold_hours), 2) AS avg_released_hours,
    ROUND(MAX(hold_hours), 2) AS max_released_hours
  FROM filtered
  WHERE is_released = 1
),
on_hold_agg AS (
  SELECT
    ROUND(AVG(hold_hours), 2) AS avg_on_hold_hours,
    ROUND(MAX(hold_hours), 2) AS max_on_hold_hours
  FROM filtered
  WHERE is_released = 0
),
bucketed AS (
  SELECT
    CASE
      WHEN hold_hours < 4 THEN '<4h'
      WHEN hold_hours < 24 THEN '4-24h'
      WHEN hold_hours < 72 THEN '1-3d'
      ELSE '>3d'
    END AS range_label,
    qty
  FROM filtered
),
bucket_counts AS (
  SELECT
    range_label,
    COUNT(*) AS item_count,
    SUM(qty) AS qty
  FROM bucketed
  GROUP BY range_label
),
totals AS (
  SELECT SUM(qty) AS total_qty FROM bucket_counts
),
buckets AS (
  SELECT '<4h' AS range_label, 1 AS order_key FROM dual
  UNION ALL
  SELECT '4-24h' AS range_label, 2 AS order_key FROM dual
  UNION ALL
  SELECT '1-3d' AS range_label, 3 AS order_key FROM dual
  UNION ALL
  SELECT '>3d' AS range_label, 4 AS order_key FROM dual
)
SELECT
  b.range_label,
  NVL(c.item_count, 0) AS item_count,
  NVL(c.qty, 0) AS qty,
  CASE
    WHEN t.total_qty = 0 THEN 0
    ELSE ROUND(NVL(c.qty, 0) * 100 / t.total_qty, 2)
  END AS pct,
  b.order_key,
  NVL(r.avg_released_hours, 0) AS avg_released_hours,
  NVL(r.max_released_hours, 0) AS max_released_hours,
  NVL(o.avg_on_hold_hours, 0) AS avg_on_hold_hours,
  NVL(o.max_on_hold_hours, 0) AS max_on_hold_hours
FROM buckets b
LEFT JOIN bucket_counts c ON c.range_label = b.range_label
CROSS JOIN totals t
CROSS JOIN released_agg r
CROSS JOIN on_hold_agg o
ORDER BY b.order_key
