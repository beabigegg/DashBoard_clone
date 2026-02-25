-- Reject History Dimension Pareto (generic dimension grouping)
-- Template slots:
--   BASE_WITH_CTE (base reject-history daily dataset SQL wrapped as CTE)
--   METRIC_COLUMN (metric expression: b.REJECT_TOTAL_QTY or b.DEFECT_QTY)
--   WHERE_CLAUSE (QueryBuilder-generated WHERE clause against alias b)
--   DIMENSION_COLUMN (column to group by, e.g. b.PJ_TYPE, b.PRODUCTLINENAME)
--   DIMENSION_ALIAS (output alias, e.g. DIMENSION_VALUE)

{{ BASE_WITH_CTE }},
dim_agg AS (
    SELECT
        {{ DIMENSION_COLUMN }} AS DIMENSION_VALUE,
        SUM({{ METRIC_COLUMN }}) AS METRIC_VALUE,
        SUM(b.MOVEIN_QTY) AS MOVEIN_QTY,
        SUM(b.REJECT_TOTAL_QTY) AS REJECT_TOTAL_QTY,
        SUM(b.DEFECT_QTY) AS DEFECT_QTY,
        SUM(b.AFFECTED_LOT_COUNT) AS AFFECTED_LOT_COUNT
    FROM base b
    {{ WHERE_CLAUSE }}
    GROUP BY
        {{ DIMENSION_COLUMN }}
    HAVING SUM({{ METRIC_COLUMN }}) > 0
)
SELECT
    DIMENSION_VALUE,
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
            ORDER BY METRIC_VALUE DESC, DIMENSION_VALUE
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) * 100 / NULLIF(SUM(METRIC_VALUE) OVER (), 0),
        4
    ) AS CUM_PCT
FROM dim_agg
ORDER BY METRIC_VALUE DESC, DIMENSION_VALUE
