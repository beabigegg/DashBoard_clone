## ADDED Requirements

### Requirement: LDAP Authentication Endpoint Configuration SHALL Be Strictly Validated
The system MUST validate LDAP authentication endpoint configuration before use, including HTTPS scheme enforcement and host allowlist checks.

#### Scenario: Invalid LDAP URL configuration detected
- **WHEN** `LDAP_API_URL` is missing, non-HTTPS, or points to a host outside the configured allowlist
- **THEN** the service MUST reject LDAP authentication calls and emit actionable diagnostics without sending credentials to that endpoint

#### Scenario: Valid LDAP URL configuration accepted
- **WHEN** `LDAP_API_URL` uses HTTPS and host is allowlisted
- **THEN** LDAP authentication requests MAY proceed with normal timeout and error handling behavior

### Requirement: Security Response Headers SHALL Be Applied Globally
All HTTP responses MUST include baseline security headers suitable for dashboard and API traffic.

#### Scenario: Standard response emitted
- **WHEN** any route returns a response
- **THEN** response MUST include `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`, and `Referrer-Policy`

#### Scenario: Production transport hardening
- **WHEN** runtime environment is production
- **THEN** response MUST include `Strict-Transport-Security`

### Requirement: Pagination Input Boundaries SHALL Be Enforced
Endpoints accepting pagination parameters MUST enforce lower and upper bounds before query execution.

#### Scenario: Negative or zero pagination inputs
- **WHEN** client sends `page <= 0` or `page_size <= 0`
- **THEN** server MUST normalize values to minimum supported bounds

#### Scenario: Excessive page size requested
- **WHEN** client sends `page_size` above configured maximum
- **THEN** server MUST clamp to maximum supported page size
