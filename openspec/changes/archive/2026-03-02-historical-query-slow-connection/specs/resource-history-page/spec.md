## MODIFIED Requirements

### Requirement: Database query execution path
The resource-history service (`resource_history_service.py`) SHALL use `read_sql_df_slow` (dedicated connection) instead of `read_sql_df` (pooled connection) for all Oracle queries.

#### Scenario: Summary parallel queries use dedicated connections
- **WHEN** the resource-history summary query executes 3 parallel queries via ThreadPoolExecutor
- **THEN** each query uses `read_sql_df_slow` and acquires a semaphore slot
- **AND** all 3 queries complete and release their slots

### Requirement: Frontend timeout
The resource-history page frontend SHALL use a 360-second API timeout for all Oracle-backed API calls.

#### Scenario: Large date range query completes
- **WHEN** a user queries resource history for a 2-year date range
- **THEN** the frontend does not abort the request for at least 360 seconds
