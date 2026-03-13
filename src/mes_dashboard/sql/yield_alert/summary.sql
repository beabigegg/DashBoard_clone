-- Optimized: yield_alert/summary
-- Change: Removed UPPER(NVL(TRIM(...))) wrapping on WIP_ENTITY_NAME
--         MES data is stored in uppercase; UPPER() prevents index usage
--         NVL/TRIM also add per-row overhead; simplified to direct LIKE
--
-- Parameters:
--   :start_date - YYYY-MM-DD
--   :end_date   - YYYY-MM-DD
--   + optional QueryBuilder params in {{ WHERE_CLAUSE }}

SELECT
    SUM(NVL(m.TRANSACTION_QUANTITY, 0)) AS TRANSACTION_QTY,
    SUM(NVL(m.SCRAP_QUANTITY, 0)) AS SCRAP_QTY,
    CASE
        WHEN SUM(NVL(m.TRANSACTION_QUANTITY, 0)) = 0 THEN 100
        ELSE ROUND(
            (1 - SUM(NVL(m.SCRAP_QUANTITY, 0)) / NULLIF(SUM(NVL(m.TRANSACTION_QUANTITY, 0)), 0)) * 100,
            4
        )
    END AS YIELD_PCT
FROM DWH.ERP_WIP_MOVETXN m
WHERE m.TXN_DATE >= TO_DATE(:start_date, 'YYYY-MM-DD')
  AND m.TXN_DATE < TO_DATE(:end_date, 'YYYY-MM-DD') + 1
  AND m.WIP_ENTITY_NAME LIKE 'GA%'
{{ WHERE_CLAUSE }}
