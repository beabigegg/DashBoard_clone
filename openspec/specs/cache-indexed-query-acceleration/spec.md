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
Query execution over cached data SHALL use prebuilt indexes for known high-frequency filter columns. Indexed columns SHALL include: `WORKCENTER_GROUP`, `PACKAGE_LEF`, `PJ_TYPE`, `FIRSTNAME`, `WAFERDESC`, `WIP_STATUS`, `HOLD_TYPE`, `LOTID`, `WORKORDER`.

#### Scenario: Filtered report query
- **WHEN** request filters target indexed fields
- **THEN** result selection MUST avoid full dataset scans and maintain existing response contract

#### Scenario: LOTID and WORKORDER use indexed access
- **WHEN** request includes `lotid` or `workorder` filter values
- **THEN** filtering MUST use the pre-built `lotid` / `workorder` index via `_lookup_positions()`
- **THEN** `_contains_any_mask()` with `str.contains()` MUST NOT be called for these fields

### Requirement: Business-Mandated Full-Table Caches SHALL Be Preserved for Resource and WIP
The system SHALL continue to maintain full-table cache behavior for `resource` and `wip` domains.

#### Scenario: Resource or WIP cache refresh
- **WHEN** cache update runs for `resource` or `wip`
- **THEN** the updater MUST retain full-table snapshot semantics and MUST NOT switch these domains to partial-only cache mode

### Requirement: Mid-section defect genealogy SHALL use CONNECT BY instead of Python BFS
The mid-section-defect genealogy resolution SHALL use `LineageEngine.resolve_full_genealogy()` (CONNECT BY NOCYCLE) instead of the existing `_bfs_split_chain()` Python BFS implementation.

#### Scenario: Genealogy cold query performance
- **WHEN** mid-section-defect analysis executes genealogy resolution with cache miss
- **THEN** `LineageEngine.resolve_split_ancestors()` SHALL be called (single CONNECT BY query)
- **THEN** response time SHALL be ≤8s (P95) for ≥50 ancestor nodes
- **THEN** Python BFS `_bfs_split_chain()` SHALL NOT be called

#### Scenario: Genealogy hot query performance
- **WHEN** mid-section-defect analysis executes genealogy resolution with L2 Redis cache hit
- **THEN** response time SHALL be ≤1s (P95)

#### Scenario: Golden test result equivalence
- **WHEN** golden test runs with ≥5 known LOTs
- **THEN** CONNECT BY output (`child_to_parent`, `cid_to_name`) SHALL be identical to BFS output for the same inputs

