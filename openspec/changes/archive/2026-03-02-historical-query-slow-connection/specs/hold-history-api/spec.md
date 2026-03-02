## MODIFIED Requirements

### Requirement: Database query execution path
The hold-history service (`hold_history_service.py`) SHALL use `read_sql_df_slow` (dedicated connection) instead of `read_sql_df` (pooled connection) for all Oracle queries.

#### Scenario: Hold history queries use dedicated connection
- **WHEN** any hold-history query is executed (trend, pareto, duration, list)
- **THEN** it uses `read_sql_df_slow` which creates a dedicated Oracle connection outside the pool
- **AND** the connection has a 300-second call_timeout (configurable)
