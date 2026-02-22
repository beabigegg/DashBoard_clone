-- Reject History Analytics (Consolidated)
-- Replaces: summary.sql, trend.sql, reason_pareto.sql
-- Template slots:
--   BASE_WITH_CTE (base reject-history daily dataset SQL wrapped as CTE)
--   WHERE_CLAUSE (QueryBuilder-generated WHERE clause against alias b)

{{ BASE_WITH_CTE }}
SELECT
    TRUNC(b.TXN_DAY) AS BUCKET_DATE,
    b.LOSSREASONNAME AS REASON,
    SUM(b.MOVEIN_QTY) AS MOVEIN_QTY,
    SUM(b.REJECT_TOTAL_QTY) AS REJECT_TOTAL_QTY,
    SUM(b.DEFECT_QTY) AS DEFECT_QTY,
    SUM(b.AFFECTED_LOT_COUNT) AS AFFECTED_LOT_COUNT,
    SUM(b.AFFECTED_WORKORDER_COUNT) AS AFFECTED_WORKORDER_COUNT
FROM base b
{{ WHERE_CLAUSE }}
GROUP BY TRUNC(b.TXN_DAY), b.LOSSREASONNAME
ORDER BY BUCKET_DATE, REASON
