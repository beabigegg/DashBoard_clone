-- yield_anomaly.sql
-- DuckDB Z-score anomaly detection on yield_alert_dataset Parquet spool.
-- Expects temp view `yield_alert_src` to be registered before execution.
-- Returns lines/packages where |z_score| > threshold based on 7-day rolling window.

WITH daily_yield AS (
    SELECT
        strftime(CAST("DATE_BUCKET" AS DATE), '%Y-%m-%d') AS data_date,
        TRIM(COALESCE(CAST("LINE_NAME" AS VARCHAR), '(NA)')) AS line,
        TRIM(COALESCE(CAST("PACKAGE_NAME" AS VARCHAR), '(NA)')) AS package,
        SUM(COALESCE("TRANSACTION_QTY", 0)) AS transaction_qty,
        SUM(COALESCE("SCRAP_QTY", 0)) AS scrap_qty
    FROM yield_alert_src
    GROUP BY 1, 2, 3
),
yield_pct AS (
    SELECT
        data_date, line, package, transaction_qty, scrap_qty,
        CASE WHEN transaction_qty = 0 THEN 100.0
             ELSE ROUND((1.0 - scrap_qty / transaction_qty) * 100, 4)
        END AS yield_pct
    FROM daily_yield
    WHERE transaction_qty > 0
),
windowed AS (
    SELECT
        data_date, line, package, yield_pct,
        AVG(yield_pct) OVER w AS rolling_avg,
        STDDEV_POP(yield_pct) OVER w AS rolling_std,
        COUNT(*) OVER w AS window_count
    FROM yield_pct
    WINDOW w AS (
        PARTITION BY line, package
        ORDER BY data_date
        ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING
    )
)
SELECT
    data_date, line, package, yield_pct,
    rolling_avg, rolling_std,
    CASE WHEN rolling_std > 0
         THEN ROUND((yield_pct - rolling_avg) / rolling_std, 3)
         ELSE 0
    END AS z_score,
    window_count
FROM windowed
WHERE window_count >= 3
  AND rolling_std > 0
ORDER BY ABS(CASE WHEN rolling_std > 0
                  THEN (yield_pct - rolling_avg) / rolling_std
                  ELSE 0 END) DESC
