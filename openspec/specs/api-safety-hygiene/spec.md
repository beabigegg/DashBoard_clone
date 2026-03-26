# api-safety-hygiene Specification

## Purpose
TBD - created by archiving change residual-hardening-round3. Update Purpose after archive.
## Requirements
### Requirement: Recursive Payload Cleaning MUST Enforce Depth Safety
Routes that normalize nested payloads MUST prevent unbounded recursion depth.

#### Scenario: Deeply nested response object
- **WHEN** NaN-cleaning helper receives deeply nested list/dict payload
- **THEN** cleaning logic MUST enforce max depth or iterative traversal and return safely without recursion failure

### Requirement: Filter Source Names MUST Be Configurable
Filter cache query sources MUST NOT rely on hardcoded view names only.

#### Scenario: Environment-specific view names
- **WHEN** deployment sets custom filter-source environment variables
- **THEN** filter cache loader MUST resolve and query configured view names

### Requirement: High-Cost APIs SHALL Apply Basic Rate Guardrails
High-cost read endpoints SHALL apply configurable request-rate guardrails to reduce abuse and accidental bursts, and throttled responses SHALL be machine-readable under the standardized error contract.

#### Scenario: Burst traffic from same client
- **WHEN** a client exceeds configured request budget for guarded endpoints
- **THEN** endpoint SHALL return HTTP 429 with clear retry guidance
- **THEN** response payload SHALL include `success: false`, `error.code: TOO_MANY_REQUESTS`, and `error.message`
- **THEN** response metadata SHALL include `meta.retry_after_seconds`
- **THEN** response headers SHALL include `Retry-After`

### Requirement: Common Boolean Query Parsing SHALL Be Shared
Boolean query parsing in routes SHALL use shared helper behavior.

#### Scenario: Different routes parse include flags
- **WHEN** routes parse common boolean query parameters
- **THEN** parsing behavior MUST be consistent across routes via shared utility

### Requirement: Mid-section defect analysis endpoints SHALL apply distributed lock to prevent duplicate pipeline execution
The `/api/mid-section-defect/analysis` pipeline SHALL use a Redis distributed lock to prevent concurrent identical queries from executing the full Oracle pipeline in parallel.

#### Scenario: Two parallel requests with cold cache
- **WHEN** two requests with identical parameters arrive simultaneously and no cache exists
- **THEN** the first request SHALL acquire the lock and execute the full pipeline
- **THEN** the second request SHALL wait by polling the cache until the first request completes
- **THEN** only ONE full Oracle pipeline execution SHALL occur

#### Scenario: Lock wait timeout
- **WHEN** a waiting request does not see a cache result within 90 seconds
- **THEN** the request SHALL proceed with its own pipeline execution (fail-open)

#### Scenario: Redis unavailable
- **WHEN** Redis is unavailable during lock acquisition
- **THEN** the lock function SHALL return acquired=true (fail-open)
- **THEN** the request SHALL proceed normally without blocking

#### Scenario: Pipeline exception with lock held
- **WHEN** the pipeline throws an exception while the lock is held
- **THEN** the lock SHALL be released in a finally block
- **THEN** subsequent requests SHALL NOT be blocked by a stale lock

### Requirement: Mid-section defect routes SHALL apply rate limiting
The `/analysis`, `/analysis/detail`, and `/export` endpoints SHALL apply per-client rate limiting using the existing `configured_rate_limit` mechanism.

#### Scenario: Analysis endpoint rate limit exceeded
- **WHEN** a client sends more than 6 requests to `/api/mid-section-defect/analysis` within 60 seconds
- **THEN** the endpoint SHALL return HTTP 429 with a `Retry-After` header
- **THEN** the service function SHALL NOT be called

#### Scenario: Detail endpoint rate limit exceeded
- **WHEN** a client sends more than 15 requests to `/api/mid-section-defect/analysis/detail` within 60 seconds
- **THEN** the endpoint SHALL return HTTP 429 with a `Retry-After` header

#### Scenario: Export endpoint rate limit exceeded
- **WHEN** a client sends more than 3 requests to `/api/mid-section-defect/export` within 60 seconds
- **THEN** the endpoint SHALL return HTTP 429 with a `Retry-After` header

#### Scenario: Loss reasons endpoint not rate limited
- **WHEN** a client sends requests to `/api/mid-section-defect/loss-reasons`
- **THEN** no rate limiting SHALL be applied (endpoint is lightweight with 24h cache)

### Requirement: Mid-section defect upstream history SHALL classify workcenters in SQL
The upstream history SQL query SHALL classify `WORKCENTERNAME` into workcenter groups using Oracle `CASE WHEN` expressions, returning the full production line history without excluding any stations.

#### Scenario: Workcenter group classification in SQL
- **WHEN** the upstream history query executes
- **THEN** each row SHALL include a `WORKCENTER_GROUP` column derived from `CASE WHEN` pattern matching
- **THEN** the classification SHALL match the patterns defined in `workcenter_groups.py`

#### Scenario: Unknown workcenter name
- **WHEN** a `WORKCENTERNAME` does not match any known pattern
- **THEN** `WORKCENTER_GROUP` SHALL be NULL
- **THEN** the row SHALL still be included in the result (not filtered out)

#### Scenario: Full production line retention
- **WHEN** the upstream history is fetched for ancestor CIDs
- **THEN** ALL stations SHALL be included (cutting, welding, mid-section, testing)
- **THEN** no order-based filtering SHALL be applied

### Requirement: Mid-section defect routes and service SHALL have test coverage
Route and service test files SHALL exist and cover core behaviors.

#### Scenario: Route tests exist
- **WHEN** pytest discovers tests
- **THEN** `tests/test_mid_section_defect_routes.py` SHALL contain tests for success, parameter validation (400), service failure (500), and rate limiting (429)

#### Scenario: Service tests exist
- **WHEN** pytest discovers tests
- **THEN** `tests/test_mid_section_defect_service.py` SHALL contain tests for date validation, pagination logic, and loss reasons caching

### Requirement: Staged trace API endpoints SHALL apply rate limiting
The `/api/trace/seed-resolve`, `/api/trace/lineage`, and `/api/trace/events` endpoints SHALL apply per-client rate limiting using the existing `configured_rate_limit` mechanism.

#### Scenario: Seed-resolve rate limit exceeded
- **WHEN** a client sends more than 10 requests to `/api/trace/seed-resolve` within 60 seconds
- **THEN** the endpoint SHALL return HTTP 429 with a `Retry-After` header

#### Scenario: Lineage rate limit exceeded
- **WHEN** a client sends more than 10 requests to `/api/trace/lineage` within 60 seconds
- **THEN** the endpoint SHALL return HTTP 429 with a `Retry-After` header

#### Scenario: Events rate limit exceeded
- **WHEN** a client sends more than 15 requests to `/api/trace/events` within 60 seconds
- **THEN** the endpoint SHALL return HTTP 429 with a `Retry-After` header

### Requirement: Mid-section defect analysis endpoint SHALL internally use staged pipeline
The existing `/api/mid-section-defect/analysis` endpoint SHALL internally delegate to the staged trace pipeline while maintaining full backward compatibility.

#### Scenario: Analysis endpoint backward compatibility
- **WHEN** a client calls `GET /api/mid-section-defect/analysis` with existing query parameters
- **THEN** the response JSON structure SHALL be identical to pre-refactoring output
- **THEN** existing rate limiting (6/min analysis, 15/min detail, 3/min export) SHALL remain unchanged
- **THEN** existing distributed lock behavior SHALL remain unchanged

### Requirement: JSON payload validation failures SHALL use standardized validation error contract
Endpoints that validate JSON request bodies SHALL return deterministic machine-readable validation errors when payload parsing or shape validation fails.

#### Scenario: Invalid JSON content-type or payload
- **WHEN** an endpoint requires JSON body and receives invalid content-type, malformed JSON, or invalid payload shape
- **THEN** endpoint SHALL return HTTP 4xx with `success: false`
- **THEN** error payload SHALL expose a stable validation code and user-facing message under `error.code/error.message`

