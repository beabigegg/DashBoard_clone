## ADDED Requirements

### Requirement: Hold Overview summary endpoint SHALL reject malformed workcenter filters
`GET /api/hold-overview/summary` SHALL validate `workcenter_group` and other
supported filter fields before invoking downstream query logic.

#### Scenario: Invalid workcenter_group returns validation error
- **WHEN** `/api/hold-overview/summary` receives a malformed `workcenter_group`
- **THEN** the response SHALL return HTTP 400 or 422
- **THEN** the response SHALL use `error.code = VALIDATION_ERROR`

#### Scenario: Malformed workcenter filter does not masquerade as empty result
- **WHEN** `/api/hold-overview/summary` receives a malicious or structurally
  invalid `workcenter_group`
- **THEN** the response SHALL NOT return `success: true` with an empty dataset
- **THEN** the route SHALL reject the request before downstream summary
  computation

