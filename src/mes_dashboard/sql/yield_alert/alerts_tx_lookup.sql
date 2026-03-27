-- Transaction quantity lookup for yield alert candidates.
-- Gets TRANSACTION_QTY at the non-reason level (date, workorder, department, package, type, etc.)
-- so that scrap-only rows can reference the actual production volume for yield calculation.
-- Parameters:
--   :start_date - YYYY-MM-DD
--   :end_date   - YYYY-MM-DD
--   + optional QueryBuilder params in {{ WHERE_CLAUSE }}
SELECT
    TRUNC(d.TXN_DATE) AS DATE_BUCKET,
    NVL(TRIM(d.WIP_ENTITY_NAME), '(NA)') AS WIP_ENTITY_NAME,
    NVL(TRIM(d.DEPARTMENT_NAME), '(NA)') AS DEPARTMENT_NAME,
    NVL(TRIM(d.LINE), '(NA)') AS LINE_NAME,
    NVL(TRIM(d.PACKAGE), '(NA)') AS PACKAGE_NAME,
    NVL(TRIM(d.TYPE), '(NA)') AS TYPE_NAME,
    NVL(TRIM(d.FUNCTION), '(NA)') AS FUNCTION_NAME,
    NVL(d.OPERATION_SEQ_NUM, -1) AS OPERATION_SEQ_NUM,
    SUM(NVL(d.TRANSACTION_QUANTITY, 0)) AS TRANSACTION_QTY
FROM DWH.ERP_WIP_MOVETXN_DETAIL d
WHERE d.TXN_DATE >= TO_DATE(:start_date, 'YYYY-MM-DD')
  AND d.TXN_DATE < TO_DATE(:end_date, 'YYYY-MM-DD') + 1
  AND UPPER(NVL(TRIM(d.WIP_ENTITY_NAME), '-')) LIKE 'GA%'
  AND d.PACKAGE IS NOT NULL
  AND TRIM(d.PACKAGE) NOT IN ('N/A', 'NA', '(NA)', '(N/A)', 'NULL')
{{ WHERE_CLAUSE }}
GROUP BY
    TRUNC(d.TXN_DATE),
    NVL(TRIM(d.WIP_ENTITY_NAME), '(NA)'),
    NVL(TRIM(d.DEPARTMENT_NAME), '(NA)'),
    NVL(TRIM(d.LINE), '(NA)'),
    NVL(TRIM(d.PACKAGE), '(NA)'),
    NVL(TRIM(d.TYPE), '(NA)'),
    NVL(TRIM(d.FUNCTION), '(NA)'),
    NVL(d.OPERATION_SEQ_NUM, -1)
