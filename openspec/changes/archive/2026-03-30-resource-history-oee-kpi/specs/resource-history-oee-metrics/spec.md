## ADDED Requirements

### Requirement: OEE production facts SQL SHALL query LOTWIPHISTORY for trackout quantities
The system SHALL provide an Oracle SQL query (`oee_facts.sql`) that fetches production output (TRACKOUTQTY) per equipment per shift date from `DWH.DW_MES_LOTWIPHISTORY`.

#### Scenario: Production output aggregation
- **WHEN** the OEE facts query executes with a date range
- **THEN** it SHALL query `DW_MES_LOTWIPHISTORY` filtering by `TRACKOUTTIMESTAMP` within the shift-adjusted date range (07:30 boundary: `timestamp + 450/1440`)
- **THEN** it SHALL filter by `SPECNAME <> '成品倉'` and `WORKCENTERNAME <> '成品倉'` (no EQUIPMENTID filter — equipment filtering is applied at DuckDB view-time per design D1b)
- **THEN** it SHALL compute `SUM(TRACKOUTQTY)` per `EQUIPMENTID × SHIFT_DATE` where `SHIFT_DATE = TRUNC(TRACKOUTTIMESTAMP - 450/1440)`
- **THEN** it SHALL NOT apply ROW_NUMBER dedup — every partial trackout record is a genuine output

### Requirement: OEE production facts SQL SHALL query LOTREJECTHISTORY for NG quantities
The system SHALL join reject records to production records using a compound key without date constraint, assigning NG to the equipment that produced the lot.

#### Scenario: NG compound key join
- **WHEN** the OEE facts query computes NG quantities
- **THEN** it SHALL build a production fingerprint of `(CONTAINERID, SPECNAME, WORKCENTERNAME, EQUIPMENTID)` from `DW_MES_LOTWIPHISTORY`
- **THEN** it SHALL query `DW_MES_LOTREJECTHISTORY` with the reject date range extended ±30 days beyond the production date range
- **THEN** it SHALL JOIN on `CONTAINERID + SPECNAME + WORKCENTERNAME` (no date in the join key)
- **THEN** NG per record SHALL be `NVL(REJECTQTY,0) + NVL(STANDBYQTY,0) + NVL(QTYTOPROCESS,0) + NVL(INPROCESSQTY,0) + NVL(PROCESSEDQTY,0)` — DEFECTQTY SHALL be excluded
- **THEN** NG SHALL be assigned to the EQUIPMENTID and SHIFT_DATE from the production fingerprint

#### Scenario: Reject exclusion filters
- **WHEN** reject records are queried
- **THEN** `SPECNAME <> '成品倉'` and `WORKCENTERNAME <> '成品倉'` SHALL be applied
- **THEN** no lossreason-based exclusion SHALL be applied (no `ERP_PJ_WIP_SCRAP_REASONS_EXCLUDE` filter)
- **THEN** containers with no WIP record (TrackIn before TrackOut terminated) are naturally excluded by the JOIN

### Requirement: OEE facts output format
The SQL SHALL output a result set compatible with the existing Parquet spool pipeline.

#### Scenario: Output columns
- **WHEN** the OEE facts query completes
- **THEN** each row SHALL contain: `EQUIPMENTID` (CHAR 16), `SHIFT_DATE` (DATE), `TRACKOUT_QTY` (NUMBER), `NG_QTY` (NUMBER)
- **THEN** the result SHALL be grouped by `EQUIPMENTID, SHIFT_DATE`

### Requirement: OEE formula computation
The system SHALL compute OEE as `Availability × Yield`, with Performance fixed at 1.0.

#### Scenario: Yield calculation
- **WHEN** yield is computed for a set of equipment records
- **THEN** `yield_pct = TRACKOUT_QTY / (TRACKOUT_QTY + NG_QTY) × 100`
- **THEN** if `TRACKOUT_QTY + NG_QTY = 0`, yield_pct SHALL be 0

#### Scenario: OEE calculation
- **WHEN** OEE is computed for a set of equipment records
- **THEN** `oee_pct = availability_pct × yield_pct / 100`
- **THEN** availability_pct SHALL come from the existing E10 shift-status data
- **THEN** the result SHALL be rounded to 1 decimal place

#### Scenario: Frontend formula consistency
- **WHEN** the frontend computes OEE from API response data
- **THEN** `compute.js` SHALL export `calcYieldPct(trackout, ng)` and `calcOeePct(availability, yield)`
- **THEN** the formulas SHALL produce identical results to the backend within rounding tolerance
