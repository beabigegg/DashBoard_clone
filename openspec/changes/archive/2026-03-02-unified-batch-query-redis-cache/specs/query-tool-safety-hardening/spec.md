## MODIFIED Requirements

### Requirement: High-risk query_tool paths SHALL migrate to slow-query execution

Functions currently using `read_sql_df` (fast pool, 55s timeout) that handle unbounded or user-driven queries SHALL be migrated to `read_sql_df_slow` (dedicated connection, 300s timeout) to prevent timeout failures.

#### Scenario: Serial number resolution uses slow-query path
- **WHEN** `_resolve_by_serial_number()` executes resolver SQL queries
- **THEN** queries SHALL use `read_sql_df_slow` instead of `read_sql_df`

#### Scenario: Work order resolution uses slow-query path
- **WHEN** `_resolve_by_work_order()` executes resolver SQL queries
- **THEN** queries SHALL use `read_sql_df_slow` instead of `read_sql_df`

#### Scenario: Equipment query functions use slow-query path
- **WHEN** `get_equipment_status_hours()`, `get_equipment_lots()`, `get_equipment_materials()`, `get_equipment_rejects()`, or `get_equipment_jobs()` execute equipment SQL queries
- **THEN** queries SHALL use `read_sql_df_slow` instead of `read_sql_df`

### Requirement: High-risk query_tool paths SHALL use engine decomposition for large inputs

Selected query functions SHALL delegate to BatchQueryEngine for ID decomposition when the resolved input set is large.

#### Scenario: Large serial number batch triggers engine decomposition
- **WHEN** `_resolve_by_serial_number()` is called with more IDs than `BATCH_QUERY_ID_THRESHOLD`
- **THEN** IDs SHALL be decomposed via `decompose_by_ids()`
- **THEN** each batch SHALL be executed through the existing resolver SQL

#### Scenario: Equipment period queries use engine time decomposition
- **WHEN** equipment period queries span more than `BATCH_QUERY_TIME_THRESHOLD_DAYS`
- **THEN** the date range SHALL be decomposed via `decompose_by_time_range()`

### Requirement: Existing resolve cache strategy SHALL be reviewed for heavy query patterns

#### Scenario: Route-level short-TTL cache extended for high-repeat patterns
- **WHEN** a query pattern is identified as high-repeat (same parameters within minutes)
- **THEN** result caching SHALL be considered using `redis_df_store`
- **THEN** cache TTL SHALL align with the service's data freshness requirements
