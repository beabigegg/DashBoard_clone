## ADDED Requirements

### Requirement: Field Contract Registry SHALL Define UI/API/Export Mapping
The system SHALL maintain a field contract registry mapping UI labels, API keys, export headers, and semantic types.

#### Scenario: Contract lookup for page rendering
- **WHEN** a page renders table headers and values
- **THEN** it MUST resolve display labels and keys through the shared field contract definitions

#### Scenario: Contract lookup for export
- **WHEN** export headers are generated
- **THEN** header names MUST follow the same semantic mapping used by the page contract

### Requirement: Consistency Checks MUST Detect Contract Drift
The system MUST provide automated checks that detect mismatches between UI, API response keys, and export field definitions.

#### Scenario: Drift detection failure
- **WHEN** a page or export changes a field name without updating the contract
- **THEN** consistency checks MUST report a failing result before release
