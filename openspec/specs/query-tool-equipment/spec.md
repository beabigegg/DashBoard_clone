## Purpose
Define stable requirements for query-tool-equipment.

## Requirements

### Requirement: Equipment tab SHALL provide equipment selection with date range filtering
The equipment tab SHALL allow selecting multiple equipment and a date range for all sub-tab queries.

#### Scenario: Equipment and date selection
- **WHEN** the user opens the equipment tab
- **THEN** a MultiSelect dropdown SHALL list available equipment from `GET /api/query-tool/equipment-list`
- **THEN** date inputs SHALL default to the last 30 days
- **THEN** a query button SHALL trigger data loading for the active sub-tab

#### Scenario: Shared filter state across sub-tabs
- **WHEN** the user selects equipment and date range then switches sub-tabs
- **THEN** the filter values SHALL persist across all equipment sub-tabs
- **THEN** switching to a new sub-tab with the same filters SHALL trigger a fresh query for that sub-tab's data type

### Requirement: Equipment Production Lots sub-tab SHALL display lots processed by selected equipment
The Production Lots sub-tab SHALL show all lots processed on the selected equipment within the date range.

#### Scenario: Production lots query
- **WHEN** the user queries with selected equipment and date range
- **THEN** the system SHALL call `POST /api/query-tool/equipment-period` with `query_type: "lots"`
- **THEN** results SHALL display in a table showing CONTAINERID, SPECNAME, TRACK_IN, TRACK_OUT, QTY, EQUIPMENTNAME

#### Scenario: Partial track-out handling
- **WHEN** a lot has multiple track-out records (partial processing)
- **THEN** all records SHALL be displayed (not deduplicated)

### Requirement: Equipment Maintenance sub-tab SHALL display maintenance job records with expandable detail
The Maintenance sub-tab SHALL show maintenance jobs from `DW_MES_JOB` with cause/repair/symptom codes.

#### Scenario: Maintenance job list
- **WHEN** the user queries maintenance records
- **THEN** the system SHALL call `POST /api/query-tool/equipment-period` with `query_type: "jobs"`
- **THEN** results SHALL display: JOBID, STATUS, CAUSECODENAME, REPAIRCODENAME, SYMPTOMCODENAME, CREATE/COMPLETE dates

#### Scenario: Job detail expansion
- **WHEN** the user clicks on a maintenance job row
- **THEN** the row SHALL expand to show full detail including employee names, secondary codes, and related lot IDs (CONTAINERNAMES)

### Requirement: Equipment Scrap sub-tab SHALL display reject/defect records
The Scrap sub-tab SHALL show reject statistics grouped by loss reason for the selected equipment and date range.

#### Scenario: Scrap records query
- **WHEN** the user queries scrap records
- **THEN** the system SHALL call `POST /api/query-tool/equipment-period` with `query_type: "rejects"`
- **THEN** results SHALL display: EQUIPMENTNAME, LOSSREASONNAME, TOTAL_REJECT_QTY, TOTAL_DEFECT_QTY, AFFECTED_LOT_COUNT

### Requirement: Equipment Timeline sub-tab SHALL visualize equipment activity over time
The Timeline sub-tab SHALL render a Gantt-style timeline showing equipment status, lots processed, and maintenance events.

#### Scenario: Multi-layer timeline rendering
- **WHEN** the user views the equipment timeline
- **THEN** the timeline SHALL overlay three data layers: status bars (PRD/SBY/UDT/SDT), lot processing bars, and maintenance event markers
- **THEN** each equipment SHALL appear as a separate track row

#### Scenario: Status color coding
- **WHEN** the timeline renders status bars
- **THEN** PRD SHALL be green, SBY SHALL be amber, UDT SHALL be red, SDT SHALL be blue-gray
- **THEN** a legend SHALL be displayed showing the color mapping

#### Scenario: Maintenance marker interaction
- **WHEN** the user hovers over or clicks a maintenance event marker on the timeline
- **THEN** a tooltip or expanded panel SHALL show the job detail (CAUSECODENAME, REPAIRCODENAME, SYMPTOMCODENAME)

### Requirement: Each equipment sub-tab SHALL support CSV export
Every equipment sub-tab SHALL have its own export button calling the existing export API.

#### Scenario: Equipment CSV export
- **WHEN** the user clicks export on any equipment sub-tab
- **THEN** the system SHALL call `POST /api/query-tool/export-csv` with the appropriate `export_type` (equipment_lots, equipment_jobs, equipment_rejects)
- **THEN** the exported params SHALL include the current equipment_ids/equipment_names and date range

### Requirement: Frontend API timeout
The query-tool equipment query, lot detail, lot jobs table, lot resolve, lot lineage, and reverse lineage composables SHALL use a 360-second API timeout for all Oracle-backed API calls.

#### Scenario: Equipment period query completes
- **WHEN** a user queries equipment history for a long period
- **THEN** the frontend does not abort the request for at least 360 seconds
