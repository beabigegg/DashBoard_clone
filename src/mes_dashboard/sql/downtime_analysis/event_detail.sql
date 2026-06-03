-- event_detail.sql
-- Per-event rows with JOB enrichment fields.
-- Executed against the spool parquet via DuckDB with pagination.

SELECT
    event_id,
    resource_id,
    status,
    reason,
    category,
    start_ts,
    end_ts,
    hours,
    fragment_count,
    match_source,
    match_ambiguous,
    job_id,
    job_order_name,
    job_model,
    symptom,
    cause,
    repair,
    wait_min,
    repair_min,
    handler
FROM downtime_events
ORDER BY start_ts DESC
LIMIT :page_size OFFSET :offset
