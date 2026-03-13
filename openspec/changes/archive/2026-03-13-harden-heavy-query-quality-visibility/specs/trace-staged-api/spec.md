## ADDED Requirements

### Requirement: Trace events responses SHALL include explicit domain and query completeness metadata
`POST /api/trace/events` responses SHALL carry completeness metadata for each requested domain and for the merged query result.

#### Scenario: Domain-level completeness fields always present
- **WHEN** events endpoint returns domain results for requested domains
- **THEN** each domain result SHALL include `quality_meta` with a valid status (`complete`, `partial`, `truncated`, or `failed`)
- **THEN** top-level response SHALL include merged `quality_meta` and `domain_quality_meta`

#### Scenario: Failed domain represented explicitly
- **WHEN** one requested domain fails during events fetch
- **THEN** response SHALL include that domain with `quality_meta.status = "failed"` and an empty data array for that domain
- **THEN** top-level completeness status SHALL remain non-complete and diagnostics SHALL identify failed scope

### Requirement: Trace events metadata SHALL remain normalized across fresh and cached responses
Completeness metadata shape SHALL be normalized identically for fresh execution and cache-hit replay.

#### Scenario: Cached response normalization
- **WHEN** events endpoint returns a cached events payload
- **THEN** response normalization SHALL ensure `quality_meta` and `domain_quality_meta` are present and schema-consistent with fresh execution responses
