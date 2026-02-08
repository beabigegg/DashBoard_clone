## Purpose
Define stable requirements for field-contract-governance.
## Requirements
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

### Requirement: Dynamic Report Rendering MUST Sanitize Untrusted Values
Dynamic table/list rendering in report and query pages SHALL sanitize untrusted text before injecting HTML.

#### Scenario: HTML-like payload in query result
- **WHEN** an API result field contains HTML-like text payload
- **THEN** the rendered page MUST display escaped text and MUST NOT execute embedded script content

### Requirement: UI Table and Download Headers SHALL Follow the Same Field Contract
Page table headers and exported file headers SHALL map to the same field contract definition for the same dataset.

#### Scenario: Header consistency check
- **WHEN** users view a report table and then export the corresponding data
- **THEN** header labels MUST remain semantically aligned and avoid conflicting naming for identical fields

### Requirement: Hold Detail Dynamic Rendering MUST Sanitize Untrusted Values
Dynamic table and distribution rendering in hold-detail SHALL sanitize untrusted text before injecting into HTML attributes or content.

#### Scenario: Hold reason distribution contains HTML-like payload
- **WHEN** workcenter/package/lot fields include HTML-like text from upstream data
- **THEN** the hold-detail page MUST render escaped text and MUST NOT execute embedded markup or scripts

