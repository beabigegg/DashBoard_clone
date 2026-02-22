-- Reject History Filter Options (Consolidated)
-- Replaces: reason_options.sql, package_options.sql, material_reason_option.sql
-- Template slots:
--   BASE_WITH_CTE (base reject-history daily dataset SQL wrapped as CTE)
--   WHERE_CLAUSE (QueryBuilder-generated WHERE clause against alias b)

{{ BASE_WITH_CTE }}
SELECT
    b.LOSSREASONNAME AS REASON,
    b.PRODUCTLINENAME AS PACKAGE,
    b.SCRAP_OBJECTTYPE,
    SUM(b.REJECT_TOTAL_QTY) AS REJECT_TOTAL_QTY,
    SUM(b.DEFECT_QTY) AS DEFECT_QTY
FROM base b
{{ WHERE_CLAUSE }}
GROUP BY b.LOSSREASONNAME, b.PRODUCTLINENAME, b.SCRAP_OBJECTTYPE
HAVING SUM(b.REJECT_TOTAL_QTY) > 0 OR SUM(b.DEFECT_QTY) > 0
