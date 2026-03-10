## ADDED Requirements

### Requirement: Yield Alert Reason Detail API SHALL return MES LOT-level reject records for a workorder and date
The API SHALL query `DWH.DW_MES_LOTREJECTHISTORY` using `PJ_WORKORDER` and `TRUNC(TXNDATE)` as filter keys, and return LOT-level reject detail rows for use in the inline reason panel.

#### Scenario: Valid workorder and date with MES records
- **WHEN** `GET /api/yield-alert/reason-detail?workorder=GA123456&date_bucket=2026-02-15` is called
- **THEN** response SHALL be `{ success: true, data: { items: [...], workorder: "GA123456", date_bucket: "2026-02-15" } }`
- **THEN** each item SHALL include: `containername`, `workcentername`, `lossreasonname`, `lossreason_code`, `rejectcomment`, `reject_qty`, `reject_total_qty`
- **THEN** items SHALL be ordered by `workcentername ASC`, `reject_total_qty DESC`

#### Scenario: Valid workorder and date with no MES records
- **WHEN** `GET /api/yield-alert/reason-detail` is called for a workorder/date that has no MES records
- **THEN** response SHALL be `{ success: true, data: { items: [], workorder: "...", date_bucket: "..." } }`
- **THEN** HTTP status SHALL be 200 (not an error)

#### Scenario: Missing required parameters
- **WHEN** `GET /api/yield-alert/reason-detail` is called without `workorder` or without `date_bucket`
- **THEN** response SHALL be `{ success: false, error: "缺少必要參數: workorder, date_bucket" }`
- **THEN** HTTP status SHALL be 400

#### Scenario: Result size safety boundary
- **WHEN** query matches more than 200 rows in MES
- **THEN** API SHALL return at most 200 rows
- **THEN** response SHALL NOT error or truncate silently without limit

#### Scenario: Case-insensitive workorder matching
- **WHEN** `workorder` parameter contains mixed-case characters (e.g., `ga123456`)
- **THEN** SQL SHALL apply `UPPER(TRIM(...))` on both parameter and column value
- **THEN** results SHALL match equivalent uppercase workorders in MES

### Requirement: Yield Alert Reason Detail SQL SHALL query MES reject history directly without dataset cache
The SQL layer SHALL execute a direct Oracle query on `DWH.DW_MES_LOTREJECTHISTORY` without depending on any dataset cache or cross-join with ERP tables.

#### Scenario: SQL bind parameters
- **WHEN** `reason_detail.sql` is executed
- **THEN** it SHALL accept exactly two bind parameters: `:workorder` (string) and `:date_bucket` (string in `YYYY-MM-DD` format)
- **THEN** the `:date_bucket` parameter SHALL be converted via `TO_DATE(:date_bucket, 'YYYY-MM-DD')`

#### Scenario: REJECT_TOTAL_QTY computation
- **WHEN** SQL returns rows
- **THEN** `REJECT_TOTAL_QTY` SHALL be computed as `REJECTQTY + STANDBYQTY + QTYTOPROCESS + INPROCESSQTY + PROCESSEDQTY` (all with NVL fallback to 0)
