-- big_category.sql
-- Aggregation of downtime hours by big category.
-- This is a DuckDB in-memory query executed against the spool parquet.
-- Parameters are injected by the service via Python string formatting.

SELECT
    category,
    SUM(hours) AS hours,
    COUNT(*) AS event_count
FROM downtime_events
GROUP BY category
ORDER BY hours DESC
