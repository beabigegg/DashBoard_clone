## ADDED Requirements

### Requirement: Reject History options endpoint SHALL reject malformed date filters
`GET /api/reject-history/options` SHALL validate incoming date filters at the
route boundary and SHALL reject malformed values with the standardized
validation-error contract.

#### Scenario: Malformed start_date returns validation error
- **WHEN** `/api/reject-history/options` receives an invalid `start_date`
- **THEN** the response SHALL return HTTP 400 or 422
- **THEN** the response SHALL use `error.code = VALIDATION_ERROR`

#### Scenario: Inverted date range returns validation error
- **WHEN** `/api/reject-history/options` receives `start_date > end_date`
- **THEN** the response SHALL return HTTP 400 or 422
- **THEN** the request SHALL NOT be treated as a successful empty-result query

