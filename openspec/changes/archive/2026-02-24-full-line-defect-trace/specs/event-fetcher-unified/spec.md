## MODIFIED Requirements

### Requirement: EventFetcher SHALL provide unified cached event querying across domains
`EventFetcher` SHALL encapsulate batch event queries with L1/L2 layered cache and rate limit bucket configuration, supporting domains: `history`, `materials`, `rejects`, `holds`, `jobs`, `upstream_history`, `downstream_rejects`.

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

#### Scenario: downstream_rejects domain query
- **WHEN** `EventFetcher` is called with domain `downstream_rejects`
- **THEN** it SHALL load `mid_section_defect/downstream_rejects.sql` via `SQLLoader.load_with_params()` with `DESCENDANT_FILTER` set to the batched IN clause condition
- **THEN** the query SHALL return reject records with `WORKCENTER_GROUP` classification
