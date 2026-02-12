# event-fetcher-unified Specification

## Purpose
TBD - created by archiving change unified-lineage-engine. Update Purpose after archive.
## Requirements
### Requirement: EventFetcher SHALL provide unified cached event querying across domains
`EventFetcher` SHALL encapsulate batch event queries with L1/L2 layered cache and rate limit bucket configuration, supporting domains: `history`, `materials`, `rejects`, `holds`, `jobs`, `upstream_history`.

#### Scenario: Cache miss for event domain query
- **WHEN** `EventFetcher` is called for a domain with container IDs and no cache exists
- **THEN** the domain query SHALL execute against Oracle via `read_sql_df()`
- **THEN** the result SHALL be stored in L2 Redis cache with key format `evt:{domain}:{sorted_cids_hash}`
- **THEN** L1 memory cache SHALL also be populated (aligned with `core/cache.py` LayeredCache pattern)

#### Scenario: Cache hit for event domain query
- **WHEN** `EventFetcher` is called for a domain and L2 Redis cache contains a valid entry
- **THEN** the cached result SHALL be returned without executing Oracle query
- **THEN** DB connection pool SHALL NOT be consumed

#### Scenario: Rate limit bucket per domain
- **WHEN** `EventFetcher` is used from a route handler
- **THEN** each domain SHALL have a configurable rate limit bucket aligned with `configured_rate_limit()` pattern
- **THEN** rate limit configuration SHALL be overridable via environment variables

