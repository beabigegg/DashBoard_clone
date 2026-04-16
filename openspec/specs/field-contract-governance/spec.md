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

### Requirement: Numeric field types SHALL be normalised at the service layer
All numeric fields surfaced by the service layer SHALL be `float` regardless of upstream Oracle type (`NUMBER`, `DECIMAL`, `BINARY_DOUBLE`).

#### Scenario: Decimal coerced to float
- **WHEN** Oracle returns a `Decimal` value
- **THEN** the service layer SHALL convert it to `float` before serialisation
- **THEN** the JSON-serialised value SHALL be a number, not a string

#### Scenario: String-encoded number coerced to float
- **WHEN** Oracle returns a numeric value as `str`
- **THEN** the service layer SHALL parse it to `float` or raise a normalised error

### Requirement: Timestamp fields SHALL be ISO-8601 UTC strings with explicit offset
All timestamp fields in JSON envelopes SHALL be ISO-8601 strings with UTC offset; no naive datetimes SHALL be emitted.

#### Scenario: Oracle TIMESTAMP serialised with offset
- **WHEN** Oracle returns a `TIMESTAMP` value
- **THEN** the envelope field SHALL be an ISO-8601 string including an explicit UTC offset suffix

#### Scenario: Oracle DATE serialised with offset
- **WHEN** Oracle returns a `DATE` value
- **THEN** the envelope field SHALL also be ISO-8601 with explicit offset (promoted to day-start in the business timezone)

### Requirement: Percentage/rate fields SHALL be rounded to fixed decimals
OEE, yield rate, and similar ratio fields SHALL be rounded to four decimal places before serialisation to prevent floating-point drift from leaking into UI formatters.

#### Scenario: OEE rounded to 4 decimals
- **WHEN** OEE is computed
- **THEN** the serialised value SHALL equal `round(value, 4)` exactly

### Requirement: Route contract matrix SHALL be the single source of truth for field shapes
`tests/fixtures/route_contract_matrix.py` SHALL register each route's expected `data` shape and SHALL be used by the envelope runtime sweep to detect field drift.

#### Scenario: New field detected without matrix update
- **WHEN** a service adds a new field to a response without updating the matrix
- **THEN** the envelope sweep SHALL emit a diagnostic identifying the drift (non-fatal in compatibility mode, fatal in strict mode)

#### Scenario: Removed field fails strict mode
- **WHEN** a field declared in the matrix is removed from the response
- **THEN** the envelope sweep SHALL fail in strict mode with a clear diagnostic

