## MODIFIED Requirements

### Requirement: High-Cost APIs SHALL Apply Basic Rate Guardrails
High-cost read endpoints SHALL apply configurable request-rate guardrails to reduce abuse and accidental bursts, and throttled responses SHALL be machine-readable under the standardized error contract.

#### Scenario: Burst traffic from same client
- **WHEN** a client exceeds configured request budget for guarded endpoints
- **THEN** endpoint SHALL return HTTP 429 with clear retry guidance
- **THEN** response payload SHALL include `success: false`, `error.code: TOO_MANY_REQUESTS`, and `error.message`
- **THEN** response metadata SHALL include `meta.retry_after_seconds`
- **THEN** response headers SHALL include `Retry-After`

## ADDED Requirements

### Requirement: JSON payload validation failures SHALL use standardized validation error contract
Endpoints that validate JSON request bodies SHALL return deterministic machine-readable validation errors when payload parsing or shape validation fails.

#### Scenario: Invalid JSON content-type or payload
- **WHEN** an endpoint requires JSON body and receives invalid content-type, malformed JSON, or invalid payload shape
- **THEN** endpoint SHALL return HTTP 4xx with `success: false`
- **THEN** error payload SHALL expose a stable validation code and user-facing message under `error.code/error.message`
