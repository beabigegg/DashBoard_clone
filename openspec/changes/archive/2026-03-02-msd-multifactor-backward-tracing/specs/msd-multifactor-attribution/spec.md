## ADDED Requirements

### Requirement: Backward tracing SHALL attribute defects to upstream materials
The system SHALL compute material-level attribution using the same pattern as machine attribution: for each material `(part_name, lot_name)` consumed by detection lots or their ancestors, calculate the defect rate among associated detection lots.

#### Scenario: Materials attribution data flow
- **WHEN** backward tracing events stage completes with `upstream_history` and `materials` domains
- **THEN** the aggregation engine SHALL build a `material_key → detection_lots` mapping where `material_key = (MATERIALPARTNAME, MATERIALLOTNAME)`
- **THEN** for each material key, `attributed_defect_rate = Σ(REJECTQTY of associated detection lots) / Σ(TRACKINQTY of associated detection lots) × 100`

#### Scenario: Materials domain requested in backward trace
- **WHEN** the frontend executes backward tracing with `mid_section_defect` profile
- **THEN** the events stage SHALL request domains `['upstream_history', 'materials']`
- **THEN** the `materials` domain SHALL use the existing EventFetcher materials domain (querying `LOTMATERIALSHISTORY`)

#### Scenario: Materials Pareto chart rendering
- **WHEN** materials attribution data is available
- **THEN** the frontend SHALL render a Pareto chart titled「依原物料歸因」
- **THEN** each bar SHALL represent a `material_part_name (material_lot_name)` combination
- **THEN** the chart SHALL show Top 10 items sorted by defect_qty, with remaining items grouped as「其他」
- **THEN** tooltip SHALL display: material name, material lot, defect count, input count, defect rate, cumulative %, and associated LOT count

#### Scenario: Material with no lot name
- **WHEN** a material record has `MATERIALLOTNAME` as NULL or empty
- **THEN** the material key SHALL use `material_part_name` only (without lot suffix)
- **THEN** display label SHALL show the part name without parenthetical lot

### Requirement: Backward tracing SHALL attribute defects to wafer root ancestors
The system SHALL compute root-ancestor-level attribution by identifying the split chain root for each detection lot and calculating defect rates per root.

#### Scenario: Root ancestor identification
- **WHEN** lineage stage returns `ancestors` data (child_to_parent map)
- **THEN** the backend SHALL identify root ancestors by traversing the parent chain for each seed until reaching a container with no further parent
- **THEN** roots SHALL be returned as `{seed_container_id: root_container_name}` in the lineage response

#### Scenario: Root attribution calculation
- **WHEN** root mapping is available
- **THEN** the aggregation engine SHALL build a `root_container_name → detection_lots` mapping
- **THEN** for each root, `attributed_defect_rate = Σ(REJECTQTY) / Σ(TRACKINQTY) × 100`

#### Scenario: Wafer root Pareto chart rendering
- **WHEN** root attribution data is available
- **THEN** the frontend SHALL render a Pareto chart titled「依源頭批次歸因」
- **THEN** each bar SHALL represent a root ancestor `CONTAINERNAME`
- **THEN** the chart SHALL show Top 10 items with cumulative percentage line

#### Scenario: Detection lot with no ancestors
- **WHEN** a detection lot has no split chain ancestors (it is its own root)
- **THEN** the root mapping SHALL map the lot to its own `CONTAINERNAME`

### Requirement: Backward Pareto layout SHALL show 5 charts in machine/material/wafer/reason/detection arrangement
The backward tracing chart section SHALL display exactly 5 Pareto charts replacing the previous 6-chart layout.

#### Scenario: Chart grid layout
- **WHEN** backward analysis data is rendered
- **THEN** charts SHALL be arranged as:
  - Row 1: 依上游機台歸因 | 依原物料歸因
  - Row 2: 依源頭批次歸因 | 依不良原因
  - Row 3: 依偵測機台 (full width or single)
- **THEN** the previous「依 WORKFLOW」「依 PACKAGE」「依 TYPE」charts SHALL NOT be rendered

### Requirement: Pareto charts SHALL support sort toggle between defect count and defect rate
Each Pareto chart SHALL allow the user to switch between sorting by defect quantity and defect rate.

#### Scenario: Default sort order
- **WHEN** a Pareto chart is first rendered
- **THEN** bars SHALL be sorted by `defect_qty` descending (current behavior)

#### Scenario: Sort by rate toggle
- **WHEN** user clicks the sort toggle to「依不良率」
- **THEN** bars SHALL re-sort by `defect_rate` descending
- **THEN** cumulative percentage line SHALL recalculate based on the new sort order
- **THEN** the toggle SHALL visually indicate the active sort mode

#### Scenario: Sort toggle persistence within session
- **WHEN** user changes sort mode on one chart
- **THEN** the change SHALL only affect that specific chart (not all charts)

### Requirement: Pareto charts SHALL display an 80% cumulative reference line
Each Pareto chart SHALL include a horizontal dashed line at the 80% cumulative mark.

#### Scenario: 80% markLine rendering
- **WHEN** Pareto chart data is rendered with cumulative percentages
- **THEN** the chart SHALL display a horizontal dashed line at y=80 on the percentage axis
- **THEN** the line SHALL use a muted color (e.g., `#94a3b8`) with dotted style
- **THEN** the line label SHALL display「80%」

### Requirement: Pareto chart tooltip SHALL include LOT count
Each Pareto chart tooltip SHALL show the number of associated detection LOTs.

#### Scenario: Tooltip with LOT count
- **WHEN** user hovers over a Pareto bar
- **THEN** the tooltip SHALL display: factor name, 關聯 LOT count (with percentage of total), defect count, input count, defect rate, cumulative percentage
