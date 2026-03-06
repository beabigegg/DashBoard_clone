# event-fetcher-unified Specification

## Purpose
TBD - created by archiving change unified-lineage-engine. Update Purpose after archive.
## Requirements
### Requirement: EventFetcher SHALL provide unified cached event querying across domains
`EventFetcher` SHALL encapsulate batch event queries with L1/L2 layered cache and rate limit bucket configuration, supporting domains: `history`, `materials`, `rejects`, `holds`, `jobs`, `upstream_history`, `downstream_rejects`.

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

### Requirement: EventFetcher SHALL separate records payload from quality metadata
`EventFetcher` SHALL return domain records and completeness metadata as separate structures, and SHALL NOT inject metadata entries into the `CONTAINERID -> records` map.

#### Scenario: Truncation metadata is separated from records
- **WHEN** total fetched rows for a domain reaches `EVENT_FETCHER_MAX_TOTAL_ROWS`
- **THEN** EventFetcher SHALL stop adding more records for that domain
- **THEN** EventFetcher SHALL return `quality_meta.status = "truncated"` with row-limit details
- **THEN** returned records map SHALL contain only container-id keys mapped to record arrays

#### Scenario: Normal domain query has complete metadata
- **WHEN** a domain query completes without truncation/failure
- **THEN** EventFetcher SHALL return `quality_meta.status = "complete"`
- **THEN** EventFetcher SHALL still return records map in the same structural shape used by callers

### Requirement: EventFetcher truncation SHALL remain configurable and observable
Truncation behavior SHALL remain controlled by environment configuration and visible in logs/metadata.

#### Scenario: Configurable total-row guard
- **WHEN** operator sets `EVENT_FETCHER_MAX_TOTAL_ROWS`
- **THEN** EventFetcher SHALL enforce the configured limit at runtime
- **THEN** returned `quality_meta` SHALL include the effective limit value

#### Scenario: Truncation observability
- **WHEN** truncation is triggered
- **THEN** a warning log SHALL include domain, observed rows, and row limit
- **THEN** caller-facing metadata SHALL expose the same truncation context

