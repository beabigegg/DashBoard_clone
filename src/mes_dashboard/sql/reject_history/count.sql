-- Reject History Row Count (data integrity baseline)
-- Counts filtered rows for the given date range using the same
-- WHERE clause as the detail list query.
-- Template slots:
--   BASE_WITH_CTE (lot-level base SQL via performance_daily_lot)
--   WHERE_CLAUSE (QueryBuilder-generated WHERE clause against alias b)

{{ BASE_WITH_CTE }}
SELECT COUNT(*) AS row_count
FROM base b
{{ WHERE_CLAUSE }}
