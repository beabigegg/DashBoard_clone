# query-tool-service-error-contract Specification

## Purpose
TBD - created by archiving change query-tool-error-contract. Update Purpose after archive.
## Requirements
### Requirement: Service layer SHALL signal failure via typed exceptions, not error dicts
The `query_tool_service` module SHALL raise typed exceptions from `mes_dashboard.core.exceptions` to signal failure. It SHALL NOT return dict-shaped error states (e.g., `{"error": "..."}`). The exception hierarchy SHALL include at minimum: `MesServiceError` (base), `UserInputError`, `ResourceNotFoundError`, `QueryTimeoutError`, `DataContractError`, `InternalQueryError`.

#### Scenario: Invalid user input raises UserInputError
- **WHEN** a service function is called with input that fails validation (e.g., missing required field, malformed identifier)
- **THEN** the function SHALL raise `UserInputError` with a human-readable message
- **THEN** the function SHALL NOT return a dict containing an `error` key

#### Scenario: Database timeout raises QueryTimeoutError
- **WHEN** an underlying database call raises `oracledb.DatabaseError` whose code matches a known Oracle timeout (`ORA-01013`, `ORA-12170`, etc.)
- **THEN** the service function SHALL catch it and raise `QueryTimeoutError`, preserving the original exception in `cause`
- **THEN** the function SHALL NOT return a dict containing an `error` key

#### Scenario: Schema drift raises DataContractError
- **WHEN** a service function encounters a missing column, missing key, or type mismatch in a database row
- **THEN** the function SHALL raise `DataContractError` with `details={"column": ...}` (or equivalent context)

#### Scenario: Unhandled query failure raises InternalQueryError
- **WHEN** a service function catches an unexpected exception from the database layer
- **THEN** it SHALL raise `InternalQueryError`, preserving the original exception in `cause`

#### Scenario: Regression guard against legacy pattern
- **WHEN** a static check is run against `src/mes_dashboard/services/query_tool_service.py`
- **THEN** the file SHALL contain zero occurrences of the pattern `return {"error":` (or single-quoted equivalent)

### Requirement: Query-tool routes SHALL map service exceptions to standardised error responses
All HTTP route handlers in `routes/query_tool_routes.py` SHALL be wrapped with a `@map_service_errors` decorator. The decorator SHALL convert each service-layer exception class to the matching response helper from `core/response.py`. Unknown exceptions SHALL be logged with `exc_info=True` and returned via `internal_error()`.

#### Scenario: UserInputError mapped to 400
- **WHEN** a route's underlying service raises `UserInputError("請輸入 container_id")`
- **THEN** the response SHALL be HTTP 400 with envelope `{"success": false, "error": {"code": "VALIDATION_ERROR", "message": "請輸入 container_id"}, "meta": {...}}`

#### Scenario: ResourceNotFoundError mapped to 404
- **WHEN** a route's underlying service raises `ResourceNotFoundError("找不到指定的 LOT")`
- **THEN** the response SHALL be HTTP 404 with error code `NOT_FOUND`

#### Scenario: QueryTimeoutError mapped to 504
- **WHEN** a route's underlying service raises `QueryTimeoutError("查詢逾時")`
- **THEN** the response SHALL be HTTP 504 with error code `QUERY_TIMEOUT`

#### Scenario: DataContractError mapped to 500 with logging
- **WHEN** a route's underlying service raises `DataContractError("缺少欄位 STATE_NAME", details={"column": "STATE_NAME"})`
- **THEN** the response SHALL be HTTP 500 with error code `INTERNAL_ERROR`
- **THEN** an ERROR-level log entry SHALL be written including the `details` payload

#### Scenario: InternalQueryError mapped to 500 with cause logged
- **WHEN** a route's underlying service raises `InternalQueryError("查詢失敗", cause=db_exc)`
- **THEN** the response SHALL be HTTP 500 with error code `INTERNAL_ERROR`
- **THEN** an ERROR-level log entry SHALL include the original exception traceback via `exc_info`

#### Scenario: Unknown exception mapped to 500
- **WHEN** a route's underlying service raises an exception that is not a `MesServiceError` subclass
- **THEN** the decorator SHALL log the exception with `exc_info=True`
- **THEN** the response SHALL be HTTP 500 with error code `INTERNAL_ERROR`

#### Scenario: Successful response unaffected
- **WHEN** a route's underlying service returns a normal payload without raising
- **THEN** the decorator SHALL pass the payload through unchanged
- **THEN** the response envelope SHALL be `success_response(...)` as before

