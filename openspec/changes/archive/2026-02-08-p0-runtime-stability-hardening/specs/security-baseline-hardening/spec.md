## ADDED Requirements

### Requirement: Production Startup SHALL Reject Weak Session Secrets
The system MUST reject startup in non-development environments when `SECRET_KEY` is missing or configured with known insecure default values.

#### Scenario: Missing production secret key
- **WHEN** runtime starts with `FLASK_ENV` not equal to `development` and no secure secret key is configured
- **THEN** application startup MUST fail fast with an explicit configuration error

### Requirement: State-Changing Endpoints SHALL Enforce CSRF Validation
All state-changing endpoints that rely on cookie-based authentication MUST enforce CSRF token validation.

#### Scenario: Missing or invalid CSRF token
- **WHEN** a POST/PUT/PATCH/DELETE request is sent without a valid CSRF token
- **THEN** the server MUST reject the request with a client error and MUST NOT execute the mutation

### Requirement: Server-Rendered Values in JavaScript Context MUST Use Safe Serialization
Values inserted into inline JavaScript from templates MUST be serialized for JavaScript context safety.

#### Scenario: Hold reason rendered in fallback inline script
- **WHEN** server-side string values are embedded into script state payloads
- **THEN** template rendering MUST use JSON-safe serialization semantics to prevent script-context injection

### Requirement: Session Establishment SHALL Mitigate Fixation Risk
Successful admin login MUST rotate session identity material before granting authenticated privileges.

#### Scenario: Admin login success
- **WHEN** credentials are validated and admin session is created
- **THEN** session identity MUST be regenerated before storing authenticated user attributes
