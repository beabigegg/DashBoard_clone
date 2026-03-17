-- hold_outlier.sql
-- DuckDB 95th-percentile outlier detection on hold_dataset Parquet spool.
-- Expects temp view `hold_src` to be registered before execution.
-- Returns hold records exceeding the 95th-percentile duration threshold.

WITH hold_base AS (
    SELECT
        strftime(CAST("hold_day" AS DATE), '%Y-%m-%d') AS hold_day,
        TRIM(COALESCE(CAST("LOT_ID" AS VARCHAR), '(NA)')) AS lot_id,
        TRIM(COALESCE(CAST("HOLDREASONNAME" AS VARCHAR), '(未填寫)')) AS hold_reason,
        TRIM(COALESCE(CAST("WORKCENTERNAME" AS VARCHAR), '(NA)')) AS workcenter,
        COALESCE("HOLD_HOURS", 0) AS hold_hours
    FROM hold_src
    WHERE COALESCE("HOLD_HOURS", 0) > 0
),
percentile_calc AS (
    SELECT
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY hold_hours) AS p95_hours
    FROM hold_base
)
SELECT
    b.hold_day, b.lot_id, b.hold_reason, b.workcenter,
    ROUND(b.hold_hours, 2) AS hold_hours,
    ROUND(p.p95_hours, 2) AS percentile_threshold
FROM hold_base b
CROSS JOIN percentile_calc p
WHERE b.hold_hours > p.p95_hours
ORDER BY b.hold_hours DESC
