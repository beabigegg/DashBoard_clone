## ADDED Requirements

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

### Requirement: LineageEngine functions SHALL be profile-agnostic
All `LineageEngine` public functions SHALL accept `container_ids: List[str]` and return dictionary structures without binding to any specific page logic.

#### Scenario: Reuse from different pages
- **WHEN** a new page (e.g., wip-detail) needs lineage resolution
- **THEN** it SHALL be able to call `LineageEngine` functions directly without modification
- **THEN** no page-specific logic (profile, TMTT detection, etc.) SHALL exist in `LineageEngine`

### Requirement: LineageEngine SQL files SHALL reside in `sql/lineage/` directory
New SQL files SHALL follow the existing `SQLLoader` convention under `src/mes_dashboard/sql/lineage/`.

#### Scenario: SQL file organization
- **WHEN** `LineageEngine` executes queries
- **THEN** `split_ancestors.sql` and `merge_sources.sql` SHALL be loaded via `SQLLoader.load_with_params("lineage/split_ancestors", ...)`
- **THEN** the SQL files SHALL NOT reference `HM_LOTMOVEOUT` (48M row table no longer needed for genealogy)
