## ADDED Requirements

### Requirement: Forward pipeline SHALL trace surviving lots downstream
When `direction=forward`, the system SHALL execute a forward tracing pipeline: detection station rejects → forward lineage (descendants) → downstream WIP + downstream rejects → forward attribution engine.

#### Scenario: Forward pipeline stages
- **WHEN** `query_analysis(station='成型', direction='forward')` is called
- **THEN** the pipeline SHALL execute in order:
  1. Fetch detection data at 成型 station (lots with rejects in date range)
  2. Resolve forward lineage via `LineageEngine.resolve_forward_tree(detection_cids)`
  3. Collect tracked CIDs = detection CIDs ∪ all descendants
  4. Fetch WIP history for tracked CIDs (with TRACKINQTY)
  5. Fetch downstream reject records for tracked CIDs
  6. Run forward attribution engine
  7. Build KPI, charts, detail table, and trend data

#### Scenario: No descendants found
- **WHEN** forward lineage returns an empty descendants map
- **THEN** KPI SHALL show zero downstream rejects and zero downstream stations reached
- **THEN** charts and detail table SHALL be empty arrays

### Requirement: downstream_rejects.sql SHALL query reject records for tracked lots
`downstream_rejects.sql` SHALL query `DW_MES_LOTREJECTHISTORY` for batched CONTAINERIDs with the standard `WORKCENTER_GROUP` CASE WHEN classification.

#### Scenario: Downstream rejects query output columns
- **WHEN** the SQL is executed
- **THEN** it SHALL return: `CONTAINERID`, `WORKCENTERNAME`, `WORKCENTER_GROUP`, `LOSSREASONNAME`, `EQUIPMENTNAME`, `REJECT_TOTAL_QTY`, `TXNDATE`

#### Scenario: Batched IN clause for large CID sets
- **WHEN** tracked CIDs exceed 1000
- **THEN** the system SHALL batch queries in groups of 1000 (same pattern as `upstream_history.sql`)

### Requirement: upstream_history.sql SHALL include TRACKINQTY
The `upstream_history.sql` query SHALL include `h.TRACKINQTY` in both the `ranked_history` CTE and the final SELECT output.

#### Scenario: TRACKINQTY in output
- **WHEN** the SQL is executed
- **THEN** each row SHALL include `TRACKINQTY` representing the input quantity at that station
- **THEN** NULL values SHALL be handled as 0 via COALESCE

### Requirement: Forward attribution engine SHALL compute per-station reject rates
The forward attribution engine SHALL aggregate reject data by downstream station (stations with order > detection station's order) and compute reject rates using TRACKINQTY as denominator.

#### Scenario: Forward attribution calculation
- **WHEN** tracked lots reach downstream station Y with total TRACKINQTY=1000 and REJECT_TOTAL_QTY=50
- **THEN** station Y's reject rate SHALL be `50 / 1000 × 100 = 5.0%`

#### Scenario: Only downstream stations included
- **WHEN** detection station is 成型 (order=4)
- **THEN** attribution SHALL only include stations with order > 4 (去膠, 水吹砂, 電鍍, 移印, 切彎腳, 元件切割, 測試)
- **THEN** stations with order ≤ 4 SHALL be excluded from forward attribution

#### Scenario: Zero input quantity guard
- **WHEN** a downstream station has TRACKINQTY sum = 0 for tracked lots
- **THEN** reject rate SHALL be 0 (not division error)

### Requirement: Forward KPI SHALL summarize downstream impact
Forward direction KPI SHALL include: detection lot count, detection defect quantity, tracked lot count (detection + descendants), downstream stations reached, downstream total rejects, and overall downstream reject rate.

#### Scenario: Forward KPI fields
- **WHEN** forward analysis completes
- **THEN** KPI SHALL contain `detection_lot_count`, `detection_defect_qty`, `tracked_lot_count`, `downstream_stations_reached`, `downstream_total_reject`, `downstream_reject_rate`

### Requirement: Forward charts SHALL show downstream distribution
Forward direction charts SHALL include: by_downstream_station (Pareto by station reject qty), by_downstream_machine (Pareto by equipment), by_downstream_loss_reason (Pareto by reason), by_detection_machine (Pareto by detection station equipment).

#### Scenario: Forward chart keys
- **WHEN** forward analysis completes
- **THEN** charts SHALL contain keys: `by_downstream_station`, `by_downstream_machine`, `by_downstream_loss_reason`, `by_detection_machine`

### Requirement: Forward detail table SHALL show per-lot downstream tracking
Forward direction detail table SHALL show one row per detection lot with downstream tracking summary.

#### Scenario: Forward detail columns
- **WHEN** forward detail is requested
- **THEN** each row SHALL include: CONTAINERID, DETECTION_EQUIPMENTNAME, TRACKINQTY (at detection), detection reject qty, downstream stations reached count, downstream total rejects, downstream reject rate, worst downstream station (highest reject rate)
