## MODIFIED Requirements

### Requirement: Database query execution path
The reject-history service (`reject_history_service.py` and `reject_dataset_cache.py`) SHALL use `read_sql_df_slow` (dedicated connection) instead of `read_sql_df` (pooled connection) for all Oracle queries.

#### Scenario: Primary query uses dedicated connection
- **WHEN** the reject-history primary query is executed
- **THEN** it uses `read_sql_df_slow` which creates a dedicated Oracle connection outside the pool
- **AND** the connection has a 300-second call_timeout (configurable)
- **AND** the connection is subject to the global slow query semaphore
