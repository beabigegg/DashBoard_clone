-- top_reasons.sql
-- Top-N reasons by total hours descending.
-- Executed against the spool parquet via DuckDB.

SELECT
    reason,
    status,
    SUM(hours)     AS hours,
    COUNT(*)       AS event_count,
    SUM(hours) / COUNT(*) * 60.0 AS avg_min
FROM downtime_events
GROUP BY reason, status
ORDER BY hours DESC
LIMIT :top_n
