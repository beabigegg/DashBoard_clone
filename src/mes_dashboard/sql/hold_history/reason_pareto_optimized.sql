-- Optimized: hold_history/reason_pareto
-- Change: Added HOLDTXNDATE WHERE to history_base CTE to enable index scan
--         (±1 day buffer accounts for 07:30 shift boundary)

WITH history_base AS (
  SELECT
    CASE
      WHEN TO_CHAR(h.HOLDTXNDATE, 'HH24MI') >= '0730' THEN TRUNC(h.HOLDTXNDATE) + 1
      ELSE TRUNC(h.HOLDTXNDATE)
    END AS hold_day,
    h.CONTAINERID,
    h.HOLDREASONID,
    h.HOLDREASONNAME,
    h.RELEASETXNDATE,
    NVL(h.QTY, 0) AS qty,
    CASE
      WHEN h.HOLDREASONNAME IN ({{ NON_QUALITY_REASONS }}) THEN 'non-quality'
      ELSE 'quality'
    END AS hold_type,
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
  WHERE h.HOLDTXNDATE >= TO_DATE(:start_date, 'YYYY-MM-DD') - 1
    AND h.HOLDTXNDATE <= TO_DATE(:end_date, 'YYYY-MM-DD') + 1
),
filtered AS (
  SELECT
    NVL(TRIM(HOLDREASONNAME), '(未填寫)') AS reason,
    qty
  FROM history_base
  WHERE hold_day BETWEEN TO_DATE(:start_date, 'YYYY-MM-DD') AND TO_DATE(:end_date, 'YYYY-MM-DD')
    AND (:hold_type = 'all' OR hold_type = :hold_type)
    AND (:include_new = 1
      OR (:include_on_hold = 1 AND RELEASETXNDATE IS NULL)
      OR (:include_released = 1 AND RELEASETXNDATE IS NOT NULL))
    AND rn_hold_day = 1
    AND (
      CASE
        WHEN is_future_hold = 1 AND rn_future_reason <> 1 THEN 0
        ELSE 1
      END
    ) = 1
),
grouped AS (
  SELECT
    reason,
    COUNT(*) AS item_count,
    SUM(qty) AS qty
  FROM filtered
  GROUP BY reason
),
ordered AS (
  SELECT
    reason,
    item_count,
    qty,
    SUM(qty) OVER () AS total_qty,
    SUM(qty) OVER (
      ORDER BY qty DESC, reason
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_qty
  FROM grouped
)
SELECT
  reason,
  item_count,
  qty,
  CASE
    WHEN total_qty = 0 THEN 0
    ELSE ROUND(qty * 100 / total_qty, 2)
  END AS pct,
  CASE
    WHEN total_qty = 0 THEN 0
    ELSE ROUND(running_qty * 100 / total_qty, 2)
  END AS cum_pct
FROM ordered
ORDER BY qty DESC, reason
