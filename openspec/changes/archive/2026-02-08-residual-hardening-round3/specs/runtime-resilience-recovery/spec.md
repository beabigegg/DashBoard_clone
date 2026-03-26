## ADDED Requirements

### Requirement: Health Endpoints SHALL Use Short Internal Memoization
Health and deep-health computation SHALL use a short-lived internal cache to prevent probe storms from amplifying backend load.

#### Scenario: Frequent monitor scrapes
- **WHEN** health endpoints are called repeatedly within a small window
- **THEN** service SHALL return memoized payload for up to 5 seconds in non-testing environments

#### Scenario: Testing mode
- **WHEN** app is running in testing mode
- **THEN** health endpoint memoization MUST be bypassed to preserve deterministic tests

### Requirement: Logs MUST Redact Connection Secrets
Runtime logs MUST avoid exposing DB connection credentials.

#### Scenario: Connection string appears in log message
- **WHEN** a log message contains DB URL credentials
- **THEN** logger output MUST redact password and sensitive userinfo before emission
