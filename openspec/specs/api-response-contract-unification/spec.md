# api-response-contract-unification Specification

## Purpose
TBD - created by archiving change api-contract-unification. Update Purpose after archive.
## Requirements
### Requirement: Standard JSON API endpoints SHALL return unified response envelope
All standard JSON API endpoints under the migration scope SHALL return a unified envelope via centralized response helpers.

#### Scenario: Successful standard API response
- **WHEN** a standard JSON endpoint completes successfully
- **THEN** it SHALL return `{ "success": true, "data": <payload>, "meta": { "timestamp": <iso-string> } }`
- **THEN** the response SHALL be produced via `success_response(...)` rather than manual `jsonify(...)`

#### Scenario: Failed standard API response
- **WHEN** a standard JSON endpoint returns 4xx/5xx business or validation failure
- **THEN** it SHALL return `{ "success": false, "error": { "code": <ERROR_CODE>, "message": <human-message> }, "meta": { "timestamp": <iso-string> } }`
- **THEN** the response SHALL be produced via `validation_error(...)`, `not_found_error(...)`, `internal_error(...)`, or `error_response(...)`

### Requirement: API contract migration SHALL maintain endpoint classification and exception boundaries
The system SHALL maintain an explicit endpoint classification for contract enforcement, including standard JSON endpoints and approved exceptions.

#### Scenario: Endpoint classification inventory
- **WHEN** migration governance checks run
- **THEN** each API endpoint SHALL be classified as one of: `standard-json`, `health-exception`, `stream-download-exception`, or `legacy-transition`
- **THEN** contract checks SHALL enforce envelope rules only for `standard-json` endpoints

#### Scenario: Health exception boundary
- **WHEN** `/health`, `/health/deep`, or `/health/frontend-shell` is requested
- **THEN** these endpoints SHALL keep their existing top-level response contract and SHALL NOT be forcibly wrapped into `{ success, data, meta }`

#### Scenario: Stream/download exception boundary
- **WHEN** an endpoint returns CSV/NDJSON/file streaming response
- **THEN** successful responses MAY be non-JSON payloads
- **THEN** JSON error responses from the same endpoint SHALL still follow the standardized error envelope

### Requirement: Contract rollout SHALL be wave-based and apply-gated
API contract unification SHALL be delivered in documented migration waves with per-wave acceptance criteria.

#### Scenario: Wave acceptance criteria
- **WHEN** a migration wave is marked complete
- **THEN** that wave SHALL include route updates, consuming frontend updates, and test updates for all endpoints in wave scope
- **THEN** no scoped endpoint in that wave SHALL emit legacy `{"success": false, "error": "..."}` responses

#### Scenario: Regression guardrail
- **WHEN** CI/verification checks run after a migration wave
- **THEN** legacy manual `jsonify(...)` usage count in migration scope SHALL NOT increase relative to baseline
- **THEN** newly added endpoints SHALL be compliant with standardized helper-based responses by default

### Requirement: Legacy app-level APIs SHALL be brought under helper-based response governance
API routes defined directly in `app.py` SHALL be migrated to helper-based response behavior unless explicitly classified as transition exceptions.

#### Scenario: App-level table query APIs
- **WHEN** `/api/query_table`, `/api/get_table_columns`, or `/api/get_table_info` returns JSON responses
- **THEN** responses SHALL be migrated to standardized helper output or be explicitly documented as temporary transition exceptions with a retirement plan

### Requirement: Standard error envelope SHALL include a QUERY_TIMEOUT code for upstream timeouts
The unified response helper module SHALL define a `QUERY_TIMEOUT` error code constant and a `query_timeout_error(message, details=None)` helper that returns the standard error envelope with HTTP status 504. This code SHALL be used for upstream database query timeouts so operators can distinguish them from generic service unavailability (`SERVICE_UNAVAILABLE`, 503) and from user input errors (`VALIDATION_ERROR`, 400).

#### Scenario: Helper returns 504 envelope
- **WHEN** `query_timeout_error("查詢逾時，請縮小日期範圍")` is called
- **THEN** the response SHALL be HTTP 504
- **THEN** the body SHALL be `{"success": false, "error": {"code": "QUERY_TIMEOUT", "message": "查詢逾時，請縮小日期範圍"}, "meta": {"timestamp": <iso-string>}}`

#### Scenario: Constant exposed for endpoint classification
- **WHEN** contract governance lists known error codes
- **THEN** `QUERY_TIMEOUT` SHALL appear alongside `VALIDATION_ERROR`, `NOT_FOUND`, `INTERNAL_ERROR`, `SERVICE_UNAVAILABLE`, etc.

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

