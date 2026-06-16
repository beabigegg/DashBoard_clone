-- B5 (yield-alert-spool-refactor): DEAD CODE — live Oracle summary path RETIRED.
-- query_yield_summary() now raises NotImplementedError; this SQL is no longer executed.
-- Summary data is served from the DuckDB spool via apply_cached_view.
-- Kept for reference only; safe to delete after spool-refactor rollout.
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
    SUM(NVL(m.TRANSACTION_QUANTITY, 0)) AS TRANSACTION_QTY
FROM DWH.ERP_WIP_MOVETXN m
WHERE m.TXN_DATE >= TO_DATE(:start_date, 'YYYY-MM-DD')
  AND m.TXN_DATE < TO_DATE(:end_date, 'YYYY-MM-DD') + 1
  AND m.WIP_ENTITY_NAME LIKE 'GA%'
{{ WHERE_CLAUSE }}
