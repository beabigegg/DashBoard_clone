## MODIFIED Requirements

### Requirement: Slow query timeout configuration
The query-tool service `read_sql_df_slow` call for full split/merge history SHALL use the config-driven default timeout instead of a hardcoded 120-second timeout.

#### Scenario: Full history query uses config timeout
- **WHEN** `full_history=True` split/merge query is executed
- **THEN** it uses `read_sql_df_slow` with the default timeout from `DB_SLOW_CALL_TIMEOUT_MS` (300s)
- **AND** the hardcoded `timeout_seconds=120` parameter is removed
