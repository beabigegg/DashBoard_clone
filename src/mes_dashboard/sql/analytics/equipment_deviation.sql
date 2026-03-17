-- equipment_deviation.sql
-- DuckDB OU% deviation detection on resource_dataset Parquet spool.
-- Expects temp view `resource_src` to be registered before execution.
-- Returns equipment where current OU% is more than threshold points below rolling 30-day baseline.

WITH daily_ou AS (
    SELECT
        strftime(CAST("DATA_DATE" AS DATE), '%Y-%m-%d') AS data_date,
        TRIM(COALESCE(CAST("HISTORYID" AS VARCHAR), '')) AS historyid,
        COALESCE("PRD_HOURS", 0) AS prd,
        COALESCE("SBY_HOURS", 0) AS sby,
        COALESCE("UDT_HOURS", 0) AS udt,
        COALESCE("SDT_HOURS", 0) AS sdt,
        COALESCE("EGT_HOURS", 0) AS egt,
        COALESCE("TOTAL_HOURS", 0) AS total_hours,
        CASE
            WHEN (COALESCE("PRD_HOURS",0)+COALESCE("SBY_HOURS",0)+COALESCE("UDT_HOURS",0)+
                  COALESCE("SDT_HOURS",0)+COALESCE("EGT_HOURS",0)) = 0 THEN 0.0
            ELSE ROUND(
                COALESCE("PRD_HOURS",0) /
                (COALESCE("PRD_HOURS",0)+COALESCE("SBY_HOURS",0)+COALESCE("UDT_HOURS",0)+
                 COALESCE("SDT_HOURS",0)+COALESCE("EGT_HOURS",0)) * 100, 2)
        END AS ou_pct
    FROM resource_src
    WHERE COALESCE("TOTAL_HOURS", 0) > 0
),
windowed AS (
    SELECT
        data_date, historyid, ou_pct,
        AVG(ou_pct) OVER w AS baseline_ou_pct,
        COUNT(*) OVER w AS window_count
    FROM daily_ou
    WINDOW w AS (
        PARTITION BY historyid
        ORDER BY data_date
        ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING
    )
)
SELECT
    data_date, historyid,
    ROUND(ou_pct, 2) AS current_ou_pct,
    ROUND(baseline_ou_pct, 2) AS baseline_ou_pct,
    ROUND(baseline_ou_pct - ou_pct, 2) AS deviation,
    window_count
FROM windowed
WHERE window_count >= 7
  AND baseline_ou_pct - ou_pct > 15
ORDER BY deviation DESC
