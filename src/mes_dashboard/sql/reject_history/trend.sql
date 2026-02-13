-- Reject History Trend
-- Template slots:
--   BASE_QUERY (base reject-history daily dataset SQL)
--   BUCKET_EXPR (Oracle date bucket expression, e.g. TRUNC(b.TXN_DAY))
--   WHERE_CLAUSE (QueryBuilder-generated WHERE clause against alias b)

{{ BASE_WITH_CTE }},
trend_raw AS (
    SELECT
        {{ BUCKET_EXPR }} AS BUCKET_DATE,
        SUM(b.MOVEIN_QTY) AS MOVEIN_QTY,
        SUM(b.REJECT_TOTAL_QTY) AS REJECT_TOTAL_QTY,
        SUM(b.DEFECT_QTY) AS DEFECT_QTY
    FROM base b
    {{ WHERE_CLAUSE }}
    GROUP BY {{ BUCKET_EXPR }}
)
SELECT
    BUCKET_DATE,
    MOVEIN_QTY,
    REJECT_TOTAL_QTY,
    DEFECT_QTY,
    CASE
        WHEN MOVEIN_QTY = 0 THEN 0
        ELSE ROUND(REJECT_TOTAL_QTY * 100 / MOVEIN_QTY, 4)
    END AS REJECT_RATE_PCT,
    CASE
        WHEN MOVEIN_QTY = 0 THEN 0
        ELSE ROUND(DEFECT_QTY * 100 / MOVEIN_QTY, 4)
    END AS DEFECT_RATE_PCT
FROM trend_raw
ORDER BY BUCKET_DATE
