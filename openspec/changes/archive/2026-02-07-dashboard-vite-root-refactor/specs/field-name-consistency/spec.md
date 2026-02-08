## ADDED Requirements

### Requirement: UI and Export Fields SHALL Have a Consistent Contract
The system SHALL define and apply a consistent contract among UI column labels, API keys, and export headers for report/query pages.

#### Scenario: Job query export naming consistency
- **WHEN** job query exports include cause/repair/symptom values
- **THEN** exported field names SHALL reflect semantic value type consistently (e.g., code name vs status name)

#### Scenario: Resource history field alignment
- **WHEN** resource history detail table shows KPI columns
- **THEN** columns required by export semantics (including Availability%) SHALL be present or explicitly mapped
