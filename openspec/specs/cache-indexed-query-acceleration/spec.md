# cache-indexed-query-acceleration Specification

## Purpose
TBD - created by archiving change p1-cache-query-efficiency. Update Purpose after archive.
## Requirements
### Requirement: Incremental Synchronization SHALL Use Versioned Watermarks
For heavy non-full-snapshot datasets, cache refresh SHALL support incremental synchronization keyed by stable version or watermark boundaries.

#### Scenario: Incremental refresh cycle
- **WHEN** source data version indicates partial changes since last sync
- **THEN** cache update logic MUST fetch and merge only changed partitions while preserving correctness guarantees

### Requirement: Query Paths SHALL Use Indexed Access for High-Frequency Filters
Query execution over cached data SHALL use prebuilt indexes for known high-frequency filter columns.

#### Scenario: Filtered report query
- **WHEN** request filters target indexed fields
- **THEN** result selection MUST avoid full dataset scans and maintain existing response contract

### Requirement: Business-Mandated Full-Table Caches SHALL Be Preserved for Resource and WIP
The system SHALL continue to maintain full-table cache behavior for `resource` and `wip` domains.

#### Scenario: Resource or WIP cache refresh
- **WHEN** cache update runs for `resource` or `wip`
- **THEN** the updater MUST retain full-table snapshot semantics and MUST NOT switch these domains to partial-only cache mode

