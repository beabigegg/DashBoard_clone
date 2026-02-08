## ADDED Requirements

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
