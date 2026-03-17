-- reject_spike.sql
-- DuckDB moving-average spike detection on reject_dataset Parquet spool.
-- Expects temp view `reject_src` to be registered before execution.
-- Returns workcenter groups where current rate > baseline * (1 + threshold).

WITH daily_rate AS (
    SELECT
        strftime(CAST("TXN_DAY" AS DATE), '%Y-%m-%d') AS data_date,
        TRIM(COALESCE(CAST("WORKCENTER_GROUP" AS VARCHAR), '(NA)')) AS workcenter_group,
        SUM(COALESCE("MOVEIN_QTY", 0)) AS movein_qty,
        SUM(COALESCE("REJECT_TOTAL_QTY", 0)) AS reject_qty
    FROM reject_src
    GROUP BY 1, 2
),
rate_with_pct AS (
    SELECT
        data_date, workcenter_group, movein_qty, reject_qty,
        CASE WHEN movein_qty = 0 THEN 0.0
             ELSE ROUND(reject_qty / movein_qty * 100, 4)
        END AS reject_rate_pct
    FROM daily_rate
    WHERE movein_qty > 0
),
windowed AS (
    SELECT
        data_date, workcenter_group, reject_rate_pct,
        AVG(reject_rate_pct) OVER w AS baseline_rate,
        COUNT(*) OVER w AS window_count
    FROM rate_with_pct
    WINDOW w AS (
        PARTITION BY workcenter_group
        ORDER BY data_date
        ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING
    )
)
SELECT
    data_date, workcenter_group, reject_rate_pct AS current_rate,
    baseline_rate,
    CASE WHEN baseline_rate > 0
         THEN ROUND((reject_rate_pct - baseline_rate) / baseline_rate * 100, 2)
         ELSE NULL
    END AS pct_change,
    window_count
FROM windowed
WHERE window_count >= 3
  AND baseline_rate > 0
  AND reject_rate_pct > baseline_rate * 1.5
ORDER BY pct_change DESC
