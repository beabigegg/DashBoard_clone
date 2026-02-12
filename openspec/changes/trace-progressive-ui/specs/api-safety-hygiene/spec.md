## MODIFIED Requirements

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
