## ADDED Requirements

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
