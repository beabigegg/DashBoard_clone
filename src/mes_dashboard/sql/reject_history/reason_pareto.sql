-- Reject History Reason Pareto
-- Template slots:
--   BASE_QUERY (base reject-history daily dataset SQL)
--   METRIC_COLUMN (metric expression: b.REJECT_TOTAL_QTY or b.DEFECT_QTY)
--   WHERE_CLAUSE (QueryBuilder-generated WHERE clause against alias b)

{{ BASE_WITH_CTE }},
reason_agg AS (
    SELECT
        b.LOSSREASONNAME AS REASON,
        SUM({{ METRIC_COLUMN }}) AS METRIC_VALUE,
        SUM(b.MOVEIN_QTY) AS MOVEIN_QTY,
        SUM(b.REJECT_TOTAL_QTY) AS REJECT_TOTAL_QTY,
        SUM(b.DEFECT_QTY) AS DEFECT_QTY,
        SUM(b.AFFECTED_LOT_COUNT) AS AFFECTED_LOT_COUNT
    FROM base b
    {{ WHERE_CLAUSE }}
    GROUP BY
        b.LOSSREASONNAME
    HAVING SUM({{ METRIC_COLUMN }}) > 0
)
SELECT
    REASON,
    METRIC_VALUE,
    MOVEIN_QTY,
    REJECT_TOTAL_QTY,
    DEFECT_QTY,
    AFFECTED_LOT_COUNT,
    ROUND(
        METRIC_VALUE * 100 / NULLIF(SUM(METRIC_VALUE) OVER (), 0),
        4
    ) AS PCT,
    ROUND(
        SUM(METRIC_VALUE) OVER (
            ORDER BY METRIC_VALUE DESC, REASON
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) * 100 / NULLIF(SUM(METRIC_VALUE) OVER (), 0),
        4
    ) AS CUM_PCT
FROM reason_agg
ORDER BY METRIC_VALUE DESC, REASON
