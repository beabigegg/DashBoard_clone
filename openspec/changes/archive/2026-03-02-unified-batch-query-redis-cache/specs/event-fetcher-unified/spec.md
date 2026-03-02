## MODIFIED Requirements

### Requirement: EventFetcher SHALL provide unified cached event querying across domains
`EventFetcher` SHALL encapsulate batch event queries with L1/L2 layered cache and rate limit bucket configuration, supporting domains: `history`, `materials`, `rejects`, `holds`, `jobs`, `upstream_history`, `downstream_rejects`. EventFetcher MAY optionally delegate ID batching to `BatchQueryEngine` for consistent decomposition patterns.

#### Scenario: Cache miss for event domain query
- **WHEN** `EventFetcher` is called for a domain with container IDs and no cache exists
- **THEN** the domain query SHALL execute against Oracle via `read_sql_df_slow()` (non-pooled dedicated connection)
- **THEN** each batch query SHALL use `timeout_seconds=60`
- **THEN** the result SHALL be stored in L2 Redis cache with key format `evt:{domain}:{sorted_cids_hash}` if CID count is within cache threshold
- **THEN** L1 memory cache SHALL also be populated if CID count is within cache threshold

#### Scenario: Cache hit for event domain query
- **WHEN** `EventFetcher` is called for a domain and L2 Redis cache contains a valid entry
- **THEN** the cached result SHALL be returned without executing Oracle query
- **THEN** DB connection pool SHALL NOT be consumed

#### Scenario: Rate limit bucket per domain
- **WHEN** `EventFetcher` is used from a route handler
- **THEN** each domain SHALL have a configurable rate limit bucket aligned with `configured_rate_limit()` pattern
- **THEN** rate limit configuration SHALL be overridable via environment variables

#### Scenario: Large CID set exceeds cache threshold
- **WHEN** the normalized CID count exceeds `CACHE_SKIP_CID_THRESHOLD` (default 10000, env: `EVENT_FETCHER_CACHE_SKIP_CID_THRESHOLD`)
- **THEN** EventFetcher SHALL skip both L1 and L2 cache writes
- **THEN** a warning log SHALL be emitted with domain name, CID count, and threshold value
- **THEN** the query result SHALL still be returned to the caller

#### Scenario: Batch concurrency default
- **WHEN** EventFetcher processes batches for a domain with >1000 CIDs
- **THEN** the default `EVENT_FETCHER_MAX_WORKERS` SHALL be 2 (env: `EVENT_FETCHER_MAX_WORKERS`)

#### Scenario: Optional BatchQueryEngine integration
- **WHEN** EventFetcher is refactored to use `BatchQueryEngine` (optional, not required)
- **THEN** `decompose_by_ids()` MAY replace inline batching logic
- **THEN** existing ThreadPoolExecutor + read_sql_df_slow_iter patterns SHALL be preserved as the primary implementation
- **THEN** no behavioral changes SHALL be introduced by engine integration
