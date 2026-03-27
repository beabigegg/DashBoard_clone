## MODIFIED Requirements

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
