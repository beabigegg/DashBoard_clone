## MODIFIED Requirements

### Requirement: Database query execution path
The reject-history service (`reject_history_service.py` and `reject_dataset_cache.py`) SHALL use `read_sql_df_slow` (dedicated connection) instead of `read_sql_df` (pooled connection) for all Oracle queries. For large queries, `BatchQueryEngine` SHALL decompose by time range or ID count.

#### Scenario: Primary query uses dedicated connection
- **WHEN** the reject-history primary query is executed
- **THEN** it uses `read_sql_df_slow` which creates a dedicated Oracle connection outside the pool
- **AND** the connection has a 300-second call_timeout (configurable)
- **AND** the connection is subject to the global slow query semaphore

#### Scenario: Long date range triggers time decomposition (date_range mode)
- **WHEN** the primary query is in `date_range` mode and the range exceeds 60 days (configurable via `BATCH_QUERY_TIME_THRESHOLD_DAYS`)
- **THEN** the query SHALL be decomposed into ~31-day monthly chunks via `BatchQueryEngine.decompose_by_time_range()`
- **THEN** each chunk SHALL execute independently with the chunk's date sub-range as bind parameters
- **THEN** chunk results SHALL be stored individually in Redis and merged via `pd.concat`

#### Scenario: Large container ID set triggers ID decomposition (container mode)
- **WHEN** the primary query is in `container` mode (workorder/lot/wafer_lot input) and the resolved container ID count exceeds 1000
- **THEN** the container IDs SHALL be decomposed into 1000-item batches via `BatchQueryEngine.decompose_by_ids()`
- **THEN** each batch SHALL execute independently
- **THEN** batch results SHALL be merged into the final cached DataFrame

#### Scenario: Short date range or small ID set uses direct query
- **WHEN** the date range is 60 days or fewer, or resolved container IDs are 1000 or fewer
- **THEN** the existing single-query path SHALL be used without engine decomposition

#### Scenario: Memory guard on result
- **WHEN** a chunk query result exceeds `BATCH_CHUNK_MAX_MEMORY_MB`
- **THEN** the chunk SHALL be discarded and marked as failed
- **THEN** the current `limit: 999999999` pattern SHALL be replaced with a configurable `max_rows_per_chunk`
