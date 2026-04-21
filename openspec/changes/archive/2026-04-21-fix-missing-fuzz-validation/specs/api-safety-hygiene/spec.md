## ADDED Requirements

### Requirement: WIP overview summary query filters SHALL reject malformed values
`GET /api/wip/overview/summary` SHALL validate malformed query-filter values at
the route boundary and SHALL return the standardized validation error contract
instead of a successful empty result.

#### Scenario: Malformed workcenter_group returns validation error
- **WHEN** `/api/wip/overview/summary` receives a malformed `workcenter_group`
- **THEN** the response SHALL return HTTP 400 or 422 with `success: false`
- **THEN** the response SHALL expose `error.code = VALIDATION_ERROR`

#### Scenario: Invalid filter value does not fall through as empty success
- **WHEN** `/api/wip/overview/summary` receives an obviously invalid filter
  value
- **THEN** the route SHALL reject the request before summary computation
- **THEN** the response SHALL NOT be `200 success:true` with empty data

