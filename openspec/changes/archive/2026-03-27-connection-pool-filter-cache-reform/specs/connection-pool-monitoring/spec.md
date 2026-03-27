## ADDED Requirements

### Requirement: Zero direct connections
All database access MUST go through connection pools (main or slow engine). No code path SHALL use `get_db_connection()` for direct oracledb connections.

#### Scenario: Table utility functions use pool
- **WHEN** `get_table_columns()`, `get_table_data()`, or `get_table_column_metadata()` is called
- **THEN** each function SHALL use `engine.connect()` from the main pool instead of `get_db_connection()`

#### Scenario: Resource status values uses service layer
- **WHEN** the `/resource/status_values` endpoint is called
- **THEN** the route SHALL delegate to a service function that uses `read_sql_df()` (main pool)
- **AND** the route SHALL NOT import or call `get_db_connection()`

#### Scenario: Direct connection counter stays zero
- **WHEN** any API request is processed under normal operation
- **THEN** the direct connection counter SHALL remain at 0
