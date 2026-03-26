## ADDED Requirements

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
