# lineage-engine-core Specification

## Purpose
TBD - created by archiving change unified-lineage-engine. Update Purpose after archive.
## Requirements
### Requirement: LineageEngine SHALL provide unified split ancestor resolution via CONNECT BY NOCYCLE
`LineageEngine.resolve_split_ancestors()` SHALL accept a list of container IDs and return the complete split ancestry graph using a single Oracle `CONNECT BY NOCYCLE` query on `DW_MES_CONTAINER.SPLITFROMID`.

#### Scenario: Normal split chain resolution
- **WHEN** `resolve_split_ancestors()` is called with a list of container IDs
- **THEN** a single SQL query using `CONNECT BY NOCYCLE` SHALL be executed against `DW_MES_CONTAINER`
- **THEN** the result SHALL include a `child_to_parent` mapping and a `cid_to_name` mapping for all discovered ancestor nodes
- **THEN** the traversal depth SHALL be limited to `LEVEL <= 20` (equivalent to existing BFS `bfs_round > 20` guard)

#### Scenario: Large input batch exceeding Oracle IN clause limit
- **WHEN** the input `container_ids` list exceeds `ORACLE_IN_BATCH_SIZE` (1000)
- **THEN** `QueryBuilder.add_in_condition()` SHALL batch the IDs and combine results
- **THEN** all bind parameters SHALL use `QueryBuilder.params` (no string concatenation)

#### Scenario: Cyclic split references in data
- **WHEN** `DW_MES_CONTAINER.SPLITFROMID` contains cyclic references
- **THEN** `NOCYCLE` SHALL prevent infinite traversal
- **THEN** the query SHALL return all non-cyclic ancestors up to `LEVEL <= 20`

#### Scenario: CONNECT BY performance regression
- **WHEN** Oracle 19c execution plan for `CONNECT BY NOCYCLE` performs worse than expected
- **THEN** the SQL file SHALL contain a commented-out recursive `WITH` (recursive subquery factoring) alternative that can be swapped in without code changes

### Requirement: LineageEngine SHALL provide unified merge source resolution
`LineageEngine.resolve_merge_sources()` SHALL accept a list of container IDs and return merge source mappings from `DW_MES_PJ_COMBINEDASSYLOTS`.

#### Scenario: Merge source lookup
- **WHEN** `resolve_merge_sources()` is called with container IDs
- **THEN** the result SHALL include `{cid: [merge_source_cid, ...]}` for all containers that have merge sources
- **THEN** all queries SHALL use `QueryBuilder` bind params

### Requirement: LineageEngine SHALL provide combined genealogy resolution
`LineageEngine.resolve_full_genealogy()` SHALL combine split ancestors and merge sources into a complete genealogy graph.

#### Scenario: Full genealogy for a set of seed lots
- **WHEN** `resolve_full_genealogy()` is called with seed container IDs
- **THEN** split ancestors SHALL be resolved first via `resolve_split_ancestors()`
- **THEN** merge sources SHALL be resolved for all discovered ancestor nodes
- **THEN** the combined result SHALL be equivalent to the existing `_resolve_full_genealogy()` output in `mid_section_defect_service.py`

#### Scenario: Seed count admission control
- **WHEN** `resolve_full_genealogy()` is called with seed count exceeding `LINEAGE_MAX_SEED_COUNT`
- **THEN** the method SHALL raise `ValueError` before executing any Oracle queries

#### Scenario: RSS admission control
- **WHEN** `resolve_full_genealogy()` is called and current process RSS exceeds `LINEAGE_RSS_REJECT_MB`
- **THEN** the method SHALL raise `MemoryError` before executing any Oracle queries

### Requirement: LineageEngine functions SHALL be profile-agnostic
All `LineageEngine` public functions SHALL accept `container_ids: List[str]` and return dictionary structures without binding to any specific page logic.

#### Scenario: Reuse from different pages
- **WHEN** a new page (e.g., wip-detail) needs lineage resolution
- **THEN** it SHALL be able to call `LineageEngine` functions directly without modification
- **THEN** no page-specific logic (profile, TMTT detection, etc.) SHALL exist in `LineageEngine`

#### Scenario: Admission control is input-based not profile-based
- **WHEN** `resolve_full_genealogy()` is called from any caller (MSD, query_tool, etc.)
- **THEN** admission control (seed count limit, RSS check) SHALL apply uniformly based on input size
- **THEN** small callers (query_tool max 100 lots) SHALL never trigger admission control under normal operation

### Requirement: LineageEngine SQL files SHALL reside in `sql/lineage/` directory
New SQL files SHALL follow the existing `SQLLoader` convention under `src/mes_dashboard/sql/lineage/`.

#### Scenario: SQL file organization
- **WHEN** `LineageEngine` executes queries
- **THEN** `split_ancestors.sql` and `merge_sources.sql` SHALL be loaded via `SQLLoader.load_with_params("lineage/split_ancestors", ...)`
- **THEN** the SQL files SHALL NOT reference `HM_LOTMOVEOUT` (48M row table no longer needed for genealogy)

### Requirement: LineageEngine SHALL use non-pooled database connections
All Oracle queries executed by `LineageEngine` SHALL use `read_sql_df_slow()` (dedicated non-pooled connections) instead of `read_sql_df()` (connection pool).

#### Scenario: Lineage query does not consume pool connections
- **WHEN** `LineageEngine` executes split ancestor, merge source, or other Oracle queries
- **THEN** queries SHALL use `read_sql_df_slow()` with the default slow query timeout (300s)
- **THEN** the shared connection pool SHALL NOT be consumed by lineage queries

#### Scenario: Lineage queries respect slow query semaphore
- **WHEN** `LineageEngine` executes queries via `read_sql_df_slow()`
- **THEN** each query SHALL acquire and release a slot from the slow query semaphore (`DB_SLOW_MAX_CONCURRENT`)

