-- Reject History Material Reason Option
-- Template slots:
--   BASE_QUERY (base reject-history daily dataset SQL)
--   WHERE_CLAUSE (QueryBuilder-generated WHERE clause against alias b)

{{ BASE_WITH_CTE }}
SELECT
    CASE
        WHEN SUM(
            CASE
                WHEN UPPER(NVL(TRIM(b.SCRAP_OBJECTTYPE), '-')) = 'MATERIAL'
                THEN NVL(b.REJECT_TOTAL_QTY, 0) + NVL(b.DEFECT_QTY, 0)
                ELSE 0
            END
        ) > 0 THEN 1
        ELSE 0
    END AS HAS_MATERIAL
FROM base b
{{ WHERE_CLAUSE }}
