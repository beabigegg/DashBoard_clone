## ADDED Requirements

### Requirement: Envelope meta SHALL include an app_version field
All standard-JSON envelope responses SHALL include `meta.app_version` reflecting the currently deployed application version.

#### Scenario: Success envelope contains app_version
- **WHEN** `success_response(...)` is invoked
- **THEN** `meta.app_version` SHALL contain a non-empty version string

#### Scenario: Error envelope contains app_version
- **WHEN** any error helper (`validation_error`, `not_found_error`, `internal_error`, `error_response`) is invoked
- **THEN** `meta.app_version` SHALL contain the same version string

### Requirement: Anomaly-summary envelope SHALL disambiguate cache-miss from empty result
`analytics_routes.anomaly_summary` SHALL include a `meta.cache_state` field so clients can distinguish a cold cache from a genuinely empty result.

#### Scenario: Warm cache hit
- **WHEN** the anomaly cache is warm and contains items
- **THEN** the response SHALL carry `meta.cache_state='warm'`

#### Scenario: Cold cache fallback
- **WHEN** the anomaly cache is cold and the route returns the soft fallback
- **THEN** the response SHALL carry `meta.cache_state='cold'` AND `data.items` SHALL be `[]`

#### Scenario: Stale cache served
- **WHEN** the cache TTL has been exceeded but a stale value is served while refresh is queued
- **THEN** the response SHALL carry `meta.cache_state='stale'`

### Requirement: All registered routes SHALL be reachable by the envelope runtime sweep
Every Flask route not explicitly listed as a contract exception SHALL be exercised by the runtime envelope sweep and validated via `tests/fixtures/route_contract_matrix.py`.

#### Scenario: Route matrix completeness
- **WHEN** a new route is added to the application
- **THEN** the developer SHALL add a corresponding entry to `route_contract_matrix.py` with sample params and expected data shape

#### Scenario: Sweep coverage threshold
- **WHEN** the envelope runtime sweep executes
- **THEN** at least 90% of non-exempted routes SHALL be covered

### Requirement: Job abandonment endpoint SHALL exist for best-effort cleanup
`POST /api/job/<id>/abandon` SHALL be added for clients to signal abandonment of in-flight async jobs.

#### Scenario: Owner abandons job
- **WHEN** the session owner calls `POST /api/job/<id>/abandon`
- **THEN** the server SHALL mark the job abandoned and schedule expedited cleanup

#### Scenario: Non-owner is rejected
- **WHEN** a client without ownership calls the abandon endpoint
- **THEN** the response SHALL be `{ success:false, error:{ code:'FORBIDDEN' } }` with HTTP 403
