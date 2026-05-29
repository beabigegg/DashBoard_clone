-- equipment_detail.sql
-- Per-resource summary of downtime hours.
-- Executed against the spool parquet via DuckDB.

SELECT
    resource_id,
    SUM(CASE WHEN status = 'UDT' THEN hours ELSE 0 END) AS udt_hours,
    SUM(CASE WHEN status = 'SDT' THEN hours ELSE 0 END) AS sdt_hours,
    SUM(CASE WHEN status = 'EGT' THEN hours ELSE 0 END) AS egt_hours,
    SUM(hours)  AS total_hours,
    COUNT(*)    AS event_count,
    FIRST(reason ORDER BY hours DESC) AS top_reason
FROM downtime_events
GROUP BY resource_id
ORDER BY total_hours DESC
