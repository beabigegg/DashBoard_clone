## ADDED Requirements

### Requirement: Flask application SHALL enforce a maximum request body size
The Flask application SHALL configure `MAX_CONTENT_LENGTH` to reject oversized request bodies before they reach route handlers.

#### Scenario: Request body exceeding the limit returns 413
- **WHEN** a POST request is sent with a JSON body larger than the configured limit (default 2 MB)
- **THEN** Flask SHALL return HTTP 413 Request Entity Too Large
- **THEN** the response SHALL not reach any route handler

#### Scenario: Request body within the limit is accepted
- **WHEN** a POST request is sent with a JSON body smaller than the configured limit
- **THEN** the request SHALL be processed normally

#### Scenario: Limit is configurable via environment variable
- **WHEN** the environment variable `MAX_REQUEST_BODY_MB` is set to an integer value
- **THEN** `MAX_CONTENT_LENGTH` SHALL be set to that value × 1024 × 1024
- **WHEN** `MAX_REQUEST_BODY_MB` is not set
- **THEN** the default limit SHALL be 2 MB
