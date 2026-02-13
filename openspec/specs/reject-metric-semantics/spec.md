# reject-metric-semantics Specification

## Purpose
TBD - created by archiving change reject-history-query-page. Update Purpose after archive.
## Requirements
### Requirement: Charge-off reject metric SHALL be computed from five reject component columns
The system SHALL compute `REJECT_TOTAL_QTY` as the sum of five reject-related quantity columns.

#### Scenario: Reject total formula
- **WHEN** a source record is transformed
- **THEN** `REJECT_TOTAL_QTY` SHALL equal `REJECTQTY + STANDBYQTY + QTYTOPROCESS + INPROCESSQTY + PROCESSEDQTY`
- **THEN** null component values SHALL be treated as zero

### Requirement: Defect metric SHALL remain independent from reject total
The system SHALL compute `DEFECT_QTY` only from `DEFECTQTY` and SHALL NOT merge it into `REJECT_TOTAL_QTY`.

#### Scenario: Defect independence
- **WHEN** a record has `DEFECTQTY > 0` and reject component sum equals 0
- **THEN** `DEFECT_QTY` SHALL be non-zero
- **THEN** `REJECT_TOTAL_QTY` SHALL remain 0

### Requirement: Yield-exclusion policy SHALL follow ERP exclusion table
The system SHALL use `ERP_PJ_WIP_SCRAP_REASONS_EXCLUDE` as the policy source for "not included in yield" scrap reasons.

#### Scenario: Enabled policy rows
- **WHEN** exclusion policy is evaluated
- **THEN** only rows with `ENABLE_FLAG='Y'` SHALL be considered exclusion rules

#### Scenario: Default exclusion behavior
- **WHEN** `include_excluded_scrap=false` (default)
- **THEN** source rows matching enabled exclusion reasons SHALL be excluded before computing yield-related metrics

#### Scenario: Optional inclusion override
- **WHEN** `include_excluded_scrap=true`
- **THEN** the same matched rows SHALL be included back into metric calculations

### Requirement: Move-in denominator SHALL be deduplicated at event level
The system SHALL deduplicate `MOVEIN_QTY` by event key before rate calculations.

#### Scenario: Primary dedupe key
- **WHEN** `HISTORYMAINLINEID` is present
- **THEN** only one row per `HISTORYMAINLINEID` SHALL contribute `MOVEIN_QTY`

#### Scenario: Fallback dedupe key
- **WHEN** `HISTORYMAINLINEID` is missing
- **THEN** fallback dedupe key SHALL use a deterministic composite key from transaction context

### Requirement: Reject and defect rates SHALL use the same deduplicated denominator
The system SHALL calculate percentage rates from deduplicated `MOVEIN_QTY` to ensure comparability.

#### Scenario: Reject rate formula
- **WHEN** `MOVEIN_QTY > 0`
- **THEN** `REJECT_RATE_PCT` SHALL equal `REJECT_TOTAL_QTY / MOVEIN_QTY * 100`

#### Scenario: Defect rate formula
- **WHEN** `MOVEIN_QTY > 0`
- **THEN** `DEFECT_RATE_PCT` SHALL equal `DEFECT_QTY / MOVEIN_QTY * 100`

#### Scenario: Zero denominator handling
- **WHEN** `MOVEIN_QTY = 0`
- **THEN** both rate fields SHALL return 0 and SHALL NOT raise divide-by-zero errors

### Requirement: Reject share SHALL describe reject proportion within total loss
The system SHALL calculate reject share against combined reject and defect loss quantities.

#### Scenario: Reject share formula
- **WHEN** `REJECT_TOTAL_QTY + DEFECT_QTY > 0`
- **THEN** `REJECT_SHARE_PCT` SHALL equal `REJECT_TOTAL_QTY / (REJECT_TOTAL_QTY + DEFECT_QTY) * 100`

### Requirement: Metric naming SHALL preserve semantic meaning across transformations
The system SHALL keep explicit names for charge-off reject and non-charge-off defect metrics.

#### Scenario: No ambiguous remapping
- **WHEN** service or export fields are generated
- **THEN** `REJECT_TOTAL_QTY` SHALL NOT be renamed to `DEFECT_QTY`
- **THEN** `DEFECT_QTY` SHALL refer only to `DEFECTQTY`

