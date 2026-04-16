## ADDED Requirements

### Requirement: Standard error envelope SHALL include a QUERY_TIMEOUT code for upstream timeouts
The unified response helper module SHALL define a `QUERY_TIMEOUT` error code constant and a `query_timeout_error(message, details=None)` helper that returns the standard error envelope with HTTP status 504. This code SHALL be used for upstream database query timeouts so operators can distinguish them from generic service unavailability (`SERVICE_UNAVAILABLE`, 503) and from user input errors (`VALIDATION_ERROR`, 400).

#### Scenario: Helper returns 504 envelope
- **WHEN** `query_timeout_error("查詢逾時，請縮小日期範圍")` is called
- **THEN** the response SHALL be HTTP 504
- **THEN** the body SHALL be `{"success": false, "error": {"code": "QUERY_TIMEOUT", "message": "查詢逾時，請縮小日期範圍"}, "meta": {"timestamp": <iso-string>}}`

#### Scenario: Constant exposed for endpoint classification
- **WHEN** contract governance lists known error codes
- **THEN** `QUERY_TIMEOUT` SHALL appear alongside `VALIDATION_ERROR`, `NOT_FOUND`, `INTERNAL_ERROR`, `SERVICE_UNAVAILABLE`, etc.
