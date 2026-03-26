## Purpose
Define stable requirements for field-name-consistency.
## Requirements
### Requirement: UI and Export Fields SHALL Have a Consistent Contract
The system SHALL define and apply a consistent contract among UI column labels, API keys, and export headers for report/query pages.

#### Scenario: Job query export naming consistency
- **WHEN** job query exports include cause/repair/symptom values
- **THEN** exported field names SHALL reflect semantic value type consistently (e.g., code name vs status name)

#### Scenario: Resource history field alignment
- **WHEN** resource history detail table shows KPI columns
- **THEN** columns required by export semantics (including Availability%) SHALL be present or explicitly mapped

### Requirement: Reject and defect metric names SHALL remain semantically consistent across UI/API/export
The system SHALL use explicit, stable names for charge-off reject and non-charge-off defect metrics across all output surfaces.

#### Scenario: UI and API key alignment
- **WHEN** summary/trend/list payloads are rendered on reject-history page
- **THEN** UI labels for reject metrics SHALL map to `REJECT_TOTAL_QTY` and related reject-rate fields
- **THEN** UI labels for defect metrics SHALL map to `DEFECT_QTY` and defect-rate fields

#### Scenario: Export header alignment
- **WHEN** reject-history CSV export is generated
- **THEN** CSV headers SHALL include both `REJECT_TOTAL_QTY` and `DEFECT_QTY`
- **THEN** header names SHALL preserve the same semantic meaning as API fields

### Requirement: Reject component columns SHALL be explicitly distinguished from defect columns
The system SHALL prevent ambiguous naming that collapses reject components and defect into a single term.

#### Scenario: Component and aggregate coexistence
- **WHEN** detailed records are presented
- **THEN** reject component fields (`REJECTQTY`, `STANDBYQTY`, `QTYTOPROCESS`, `INPROCESSQTY`, `PROCESSEDQTY`) SHALL be distinguishable from `DEFECT_QTY`
- **THEN** aggregate `REJECT_TOTAL_QTY` SHALL be clearly identified as component sum, not defect

