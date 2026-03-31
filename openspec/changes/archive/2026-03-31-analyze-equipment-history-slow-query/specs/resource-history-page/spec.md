## MODIFIED Requirements

### Requirement: Database query execution path
The resource-history service SHALL use `read_sql_df_slow` (dedicated connection) for all Oracle queries. The canonical spool path (`try_compute_query_from_canonical_spool`) SHALL be attempted first on every POST /query; if the spool is valid the Oracle path SHALL be skipped entirely. The spool validity window SHALL be governed by `CACHE_TTL_DATASET_SECONDS` (default 7200 seconds).

#### Scenario: Canonical spool hit skips Oracle
- **WHEN** POST /query is received and the canonical spool for the requested date range exists in Redis
- **THEN** `try_compute_query_from_canonical_spool()` SHALL return a non-None result
- **THEN** no Oracle query SHALL be executed
- **THEN** the response SHALL be returned within the DuckDB computation time (no Oracle latency)

#### Scenario: Spool remains valid across warmup cycles
- **WHEN** `CACHE_TTL_DATASET_SECONDS=7200` and `WARMUP_INTERVAL_SECONDS=3600`
- **THEN** a spool created by warmup SHALL remain valid until the next warmup fires and refreshes it
- **THEN** users querying between warmup cycles SHALL receive the cached spool, not trigger Oracle

#### Scenario: Canonical spool miss falls through to Oracle
- **WHEN** the canonical spool Redis metadata key is absent or expired
- **THEN** `execute_primary_query()` SHALL run Oracle queries
- **THEN** the result SHALL be spooled to Parquet and registered with TTL=`CACHE_TTL_DATASET_SECONDS`

#### Scenario: Summary parallel queries use dedicated connections
- **WHEN** the resource-history summary query executes parallel queries via ThreadPoolExecutor
- **THEN** each query uses `read_sql_df_slow` and acquires a semaphore slot
- **AND** all queries complete and release their slots

### Requirement: Frontend timeout
The resource-history page frontend SHALL use a 360-second API timeout for all Oracle-backed API calls.

#### Scenario: Large date range query completes
- **WHEN** a user queries resource history for a 2-year date range
- **THEN** the frontend does not abort the request for at least 360 seconds
