## Purpose
Define stable requirements for layered-route-cache.
## Requirements
### Requirement: Route Cache SHALL Use Layered Storage
The route cache SHALL use L1 in-memory TTL cache and L2 Redis JSON cache when Redis is available.

#### Scenario: L1 cache hit
- **WHEN** a cached key exists in L1 and is unexpired
- **THEN** the API response SHALL be returned from memory without querying Redis

#### Scenario: L2 fallback
- **WHEN** a cached key is missing in L1 but exists in Redis
- **THEN** the value SHALL be returned and warmed into L1

### Requirement: Cache SHALL Degrade Gracefully Without Redis
The route cache SHALL remain functional with L1 cache when Redis is unavailable.

#### Scenario: Redis unavailable at startup
- **WHEN** Redis health check fails during app initialization
- **THEN** route cache operations SHALL continue using L1 cache without application failure

### Requirement: Resource and WIP Full-Table Cache SHALL Remain the Authoritative Cached Dataset
The system MUST keep `resource` and `wip` full-table cache datasets as the canonical cached source for downstream route queries.

#### Scenario: Route query reads cached baseline
- **WHEN** an endpoint requires resource or wip data
- **THEN** it MUST read from the corresponding full-table cache baseline before applying derived filters or aggregations

### Requirement: Cache Access Paths SHALL Support Index-Based Lookup and Derived Views
The caching layer SHALL support index and derived-view access paths to reduce per-request full-table merge and transformation overhead.

#### Scenario: Lookup by key under concurrent load
- **WHEN** requests query by high-cardinality keys such as RESOURCEID
- **THEN** the system MUST serve lookups via indexed cache access instead of repeated full-array scans

### Requirement: Full-Table Cache Refresh MUST Support Incremental Derivation Updates
Derived cache indices and aggregates MUST be refreshed consistently when the underlying full-table cache version changes.

#### Scenario: Cache version update
- **WHEN** full-table cache is refreshed to a new version
- **THEN** dependent indices and derived views MUST be rebuilt or updated before being exposed for reads

