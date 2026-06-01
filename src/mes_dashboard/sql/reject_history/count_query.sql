-- Reject History Row Count for row-count chunking (USE_ROW_COUNT_CHUNKING=true)
-- Counts the full dataset rows matching the same WHERE clause as the primary query.
-- Template slots:
--   BASE_WITH_CTE (lot-level base SQL via performance_daily_lot)
--   WHERE_CLAUSE (QueryBuilder-generated WHERE clause against alias b)
-- Parameters:
--   :start_date - YYYY-MM-DD (inclusive)
--   :end_date   - YYYY-MM-DD (inclusive)

{{ BASE_WITH_CTE }}
SELECT COUNT(*) AS row_count
FROM base b
{{ WHERE_CLAUSE }}
