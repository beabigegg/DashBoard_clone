-- B5 (yield-alert-spool-refactor): DEAD CODE — live Oracle trend path RETIRED.
-- query_yield_trend() now raises NotImplementedError; this SQL is no longer executed.
-- Trend data is served from the DuckDB spool via apply_cached_view.
-- Kept for reference only; safe to delete after spool-refactor rollout.
--
-- Yield Alert trend aggregate
-- Placeholders:
--   {{ BUCKET_EXPR }}
-- Parameters:
--   :start_date - YYYY-MM-DD
--   :end_date   - YYYY-MM-DD
--   + optional QueryBuilder params in {{ WHERE_CLAUSE }}
SELECT
    {{ BUCKET_EXPR }} AS DATE_BUCKET,
    SUM(NVL(m.TRANSACTION_QUANTITY, 0)) AS TRANSACTION_QTY
FROM DWH.ERP_WIP_MOVETXN m
WHERE m.TXN_DATE >= TO_DATE(:start_date, 'YYYY-MM-DD')
  AND m.TXN_DATE < TO_DATE(:end_date, 'YYYY-MM-DD') + 1
  AND UPPER(NVL(TRIM(m.WIP_ENTITY_NAME), '-')) LIKE 'GA%'
{{ WHERE_CLAUSE }}
GROUP BY {{ BUCKET_EXPR }}
ORDER BY DATE_BUCKET ASC
