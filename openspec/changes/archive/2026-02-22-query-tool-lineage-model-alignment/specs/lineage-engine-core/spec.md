## MODIFIED Requirements

### Requirement: LineageEngine SHALL provide combined genealogy resolution
`LineageEngine.resolve_full_genealogy()` SHALL produce a semantic lineage graph that includes split, merge, wafer-origin, and GD-rework relationships.

#### Scenario: Combined genealogy includes typed edges
- **WHEN** `resolve_full_genealogy()` is called with seed container IDs
- **THEN** the response SHALL include lineage relationships with explicit edge types
- **THEN** split, merge, wafer-origin, and gd-rework edges SHALL be distinguishable

#### Scenario: GA without GC remains traceable by wafer origin
- **WHEN** seed lots have GA lineage without GC nodes
- **THEN** the engine SHALL still link GA lineage to wafer origin via `FIRSTNAME`
- **THEN** lineage output SHALL remain connected without synthetic GC nodes

#### Scenario: Backward compatibility fields preserved during migration
- **WHEN** callers still depend on legacy ancestry maps
- **THEN** the engine SHALL continue returning legacy-compatible fields during migration window
- **THEN** typed graph fields SHALL be additive, not replacing legacy fields immediately

## ADDED Requirements

### Requirement: LineageEngine SHALL resolve wafer-origin relationships from container data
The engine SHALL derive wafer-origin links using `DW_MES_CONTAINER.FIRSTNAME` and valid LOT nodes.

#### Scenario: Wafer-origin edge creation
- **WHEN** a lot node has a non-empty `FIRSTNAME` that maps to a wafer lot node
- **THEN** the engine SHALL create a `wafer_origin` edge between the lot and wafer nodes
- **THEN** wafer-origin resolution SHALL avoid duplicate edges per node pair

### Requirement: LineageEngine SHALL resolve GD rework source relationships from container data
The engine SHALL derive GD rework source links primarily from `ORIGINALCONTAINERID`, with `SPLITFROMID` as fallback.

#### Scenario: GD source via ORIGINALCONTAINERID
- **WHEN** a GD lot has a valid `ORIGINALCONTAINERID`
- **THEN** the engine SHALL create a `gd_rework_source` edge from source lot to GD lot
- **THEN** this edge SHALL be included in reverse and forward lineage outputs where applicable

#### Scenario: GD source fallback to SPLITFROMID
- **WHEN** `ORIGINALCONTAINERID` is null or invalid and `SPLITFROMID` is available
- **THEN** the engine SHALL fallback to `SPLITFROMID` for gd-rework source linkage
- **THEN** the fallback linkage SHALL be marked with edge type `gd_rework_source`
