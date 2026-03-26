## Purpose
Define stable requirements for msd-suspect-context.

## Requirements

### Requirement: Detail table SHALL display suspect factor hit counts instead of raw upstream machine list
The backward detail table SHALL replace the flat `UPSTREAM_MACHINES` string column with a structured suspect factor hit display that links to the current Pareto Top N.

#### Scenario: Suspect hit column rendering
- **WHEN** backward detail table is rendered
- **THEN** the「上游機台」column SHALL be replaced by a「嫌疑命中」column
- **THEN** each cell SHALL show the names of upstream machines that appear in the current Pareto Top N suspect list, with a hit ratio (e.g., `WIRE-03, DIE-01 (2/5)`)

#### Scenario: Suspect list derived from Pareto Top N
- **WHEN** the machine Pareto chart displays Top N machines (after any inline station/spec filters)
- **THEN** the suspect list SHALL be the set of machine names from those Top N entries
- **THEN** changing the Pareto inline filters SHALL update the suspect list and re-render the hit column

#### Scenario: Full match indicator
- **WHEN** a LOT's upstream machines include all machines in the suspect list
- **THEN** the cell SHALL display a visual indicator (e.g., star or highlight) marking full match

#### Scenario: No hits
- **WHEN** a LOT's upstream machines include none of the suspect machines
- **THEN** the cell SHALL display「-」

#### Scenario: Upstream machine count column
- **WHEN** backward detail table is rendered
- **THEN** the「上游LOT數」column SHALL remain as-is (showing ancestor count)
- **THEN** a new「上游台數」column SHALL show the total number of unique upstream machines for that LOT

### Requirement: Backend detail table SHALL return structured upstream data
The `_build_detail_table` function SHALL return upstream machines as a structured list instead of a flat comma-separated string.

#### Scenario: Structured upstream machines response
- **WHEN** backward detail API returns LOT records
- **THEN** each record's `UPSTREAM_MACHINES` field SHALL be a list of `{"station": "<workcenter_group>", "machine": "<equipment_name>"}` objects
- **THEN** the flat comma-separated string SHALL no longer be returned in this field

#### Scenario: CSV export backward compatibility
- **WHEN** CSV export is triggered for backward detail
- **THEN** the `UPSTREAM_MACHINES` column in CSV SHALL flatten the structured list back to comma-separated `station/machine` format
- **THEN** CSV format SHALL remain unchanged from current behavior

#### Scenario: Structured upstream materials response
- **WHEN** materials attribution is available
- **THEN** each detail record SHALL include an `UPSTREAM_MATERIALS` field: list of `{"part": "<material_part_name>", "lot": "<material_lot_name>"}` objects

#### Scenario: Structured wafer root response
- **WHEN** root ancestor attribution is available
- **THEN** each detail record SHALL include a `WAFER_ROOT` field: string with root ancestor `CONTAINERNAME`

### Requirement: Suspect machine context panel SHALL show machine details and recent maintenance
Clicking a machine bar in the Pareto chart SHALL open a context popover showing machine attribution details and recent maintenance history.

#### Scenario: Context panel trigger
- **WHEN** user clicks a bar in the「依上游機台歸因」Pareto chart
- **THEN** a popover panel SHALL appear near the clicked bar
- **WHEN** user clicks outside the popover or clicks the same bar again
- **THEN** the popover SHALL close

#### Scenario: Context panel content - attribution summary
- **WHEN** the context panel is displayed
- **THEN** it SHALL show: equipment name, workcenter group, resource family (RESOURCEFAMILYNAME), attributed defect rate, attributed defect count, attributed input count, associated LOT count

#### Scenario: Context panel content - recent maintenance
- **WHEN** the context panel is displayed
- **THEN** it SHALL fetch recent JOB records for the machine's equipment_id (last 30 days)
- **THEN** it SHALL display up to 5 most recent JOB records showing: JOBID, JOBSTATUS, JOBMODELNAME, CREATEDATE, COMPLETEDATE
- **WHEN** the machine has no recent JOB records
- **THEN** the maintenance section SHALL display「近 30 天無維修紀錄」

#### Scenario: Context panel loading state
- **WHEN** maintenance data is being fetched
- **THEN** the maintenance section SHALL show a loading indicator
- **THEN** the attribution summary section SHALL render immediately (data already available from attribution)

#### Scenario: Context panel for non-machine charts
- **WHEN** user clicks bars in other Pareto charts (materials, wafer root, loss reason, detection machine)
- **THEN** no context panel SHALL appear (machine context only)
