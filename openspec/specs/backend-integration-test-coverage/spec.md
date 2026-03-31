## Purpose

Ensure every route module has integration tests covering success and error paths via the Flask test client.

## Requirements

### Requirement: Every route module SHALL have integration tests covering success and error paths
Each route module under `src/mes_dashboard/routes/` SHALL have a corresponding test file that exercises HTTP endpoints via the Flask test client, covering at least one success path and one error/validation path per endpoint.

#### Scenario: Route module with missing integration tests
- **WHEN** a route module exists at `routes/<name>.py` with no corresponding `tests/test_<name>_routes.py`
- **THEN** a new integration test file SHALL be created

#### Scenario: Identified gap routes
- **WHEN** auditing the following route modules: `dashboard_routes.py`, `spool_routes.py`, `user_auth_routes.py` (beyond basic auth tests)
- **THEN** each SHALL have integration tests for all registered endpoints

### Requirement: Integration tests SHALL verify response format compliance
All route integration tests SHALL assert that responses conform to the API contract — using `success_response` / error helpers from `core/response.py`.

#### Scenario: Successful API response
- **WHEN** a test calls an endpoint that returns success
- **THEN** the response JSON SHALL contain `"success": true` and a `"data"` field

#### Scenario: Validation error response
- **WHEN** a test calls an endpoint with invalid parameters
- **THEN** the response JSON SHALL contain `"success": false` and an `"error"` field with a predefined error code

### Requirement: Integration tests SHALL cover partial-failure responses
For endpoints that support partial-failure propagation, integration tests SHALL verify that partial failure metadata is correctly included in the response.

#### Scenario: Endpoint returns partial failure
- **WHEN** one of multiple data sources fails during a multi-source query
- **THEN** the response SHALL include partial failure indicators as defined by the API contract
