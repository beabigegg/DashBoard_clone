## ADDED Requirements

### Requirement: Trace events endpoint SHALL expose domain-level quality metadata
`POST /api/trace/events` SHALL include normalized quality metadata for each requested domain and for the aggregated response.

#### Scenario: Complete events response
- **WHEN** all requested domains complete without truncation/failure
- **THEN** response SHALL include `quality_meta.status = "complete"`
- **THEN** each domain entry SHALL be marked complete in domain-level metadata

#### Scenario: Mixed quality response
- **WHEN** at least one requested domain is partial or truncated
- **THEN** response SHALL include top-level `quality_meta.status = "partial"` or `"truncated"`
- **THEN** response SHALL include per-domain quality details that identify affected domains

### Requirement: Async trace job result SHALL preserve quality metadata parity
`GET /api/trace/job/<job_id>/result` SHALL preserve the same quality metadata semantics as synchronous `/api/trace/events`.

#### Scenario: Async result metadata parity
- **WHEN** a query is routed to async job execution and later fetched by result endpoint
- **THEN** result payload SHALL include `quality_meta` equivalent to sync execution semantics
- **THEN** the metadata SHALL indicate partial/truncated states when applicable

### Requirement: NDJSON trace stream SHALL emit quality metadata event
`GET /api/trace/job/<job_id>/stream` SHALL include a dedicated NDJSON event carrying quality metadata.

#### Scenario: NDJSON quality metadata emission
- **WHEN** stream emits domain records and reaches completion
- **THEN** stream SHALL emit a `quality_meta` event before final `complete` event
- **THEN** `quality_meta` event content SHALL match the job result metadata for the same job
