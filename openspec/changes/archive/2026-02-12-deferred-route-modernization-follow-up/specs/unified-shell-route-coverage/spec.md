## MODIFIED Requirements

### Requirement: Deferred routes SHALL become shell-contract governed in this follow-up phase
All routes deferred by phase 1 (`/tables`, `/excel-query`, `/query-tool`, `/mid-section-defect`) SHALL be represented as in-scope shell contracts with complete ownership and visibility metadata.

#### Scenario: Deferred route contract promotion
- **WHEN** follow-up route coverage validation is executed
- **THEN** each deferred route SHALL have route metadata, owner metadata, and visibility/access policy metadata
- **THEN** missing metadata SHALL fail route governance validation

#### Scenario: CI gate blocks deferred route contract gaps
- **WHEN** CI evaluates route-governance completeness for this follow-up change
- **THEN** any deferred route missing required contract fields SHALL block promotion

