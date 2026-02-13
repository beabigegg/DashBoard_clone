-- Reject History Package Options
-- Template slots:
--   BASE_QUERY (base reject-history daily dataset SQL)
--   WHERE_CLAUSE (QueryBuilder-generated WHERE clause against alias b)

{{ BASE_WITH_CTE }}
SELECT
    b.PRODUCTLINENAME AS PACKAGE,
    SUM(b.REJECT_TOTAL_QTY) AS REJECT_TOTAL_QTY,
    SUM(b.DEFECT_QTY) AS DEFECT_QTY
FROM base b
{{ WHERE_CLAUSE }}
GROUP BY b.PRODUCTLINENAME
HAVING SUM(b.REJECT_TOTAL_QTY) > 0 OR SUM(b.DEFECT_QTY) > 0
ORDER BY PACKAGE
