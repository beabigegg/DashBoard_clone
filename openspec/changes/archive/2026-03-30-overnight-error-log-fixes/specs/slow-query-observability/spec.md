# Delta Spec: slow-query-observability

## ADDED Requirements

### Requirement: Per-query slow warning threshold

The fast-query path in `database.read_sql_df` SHALL log a WARNING when query elapsed time exceeds **3.0 seconds** (changed from 1.0s).

This threshold applies only to the `read_sql_df` per-query debug log line. The `metrics.py` SLOW_QUERY_THRESHOLD (env-configurable, used for operational alerting) is unaffected.

#### Scenario: Query under 3s does not trigger warning
- **WHEN** a `read_sql_df` query completes in 2.5s
- **THEN** no slow query WARNING is logged by `database.py`

#### Scenario: Query over 3s triggers warning
- **WHEN** a `read_sql_df` query completes in 4.0s
- **THEN** a slow query WARNING is logged with caller name, elapsed time, and SQL preview

#### Scenario: realtime_equipment_cache periodic refresh
- **WHEN** `realtime_equipment_cache` refresh query completes in ~2.0s (typical)
- **THEN** no slow query WARNING is logged (below 3.0s threshold)
