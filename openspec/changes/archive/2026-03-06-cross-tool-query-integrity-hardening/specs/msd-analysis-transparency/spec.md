## ADDED Requirements

### Requirement: MSD aggregation pipeline SHALL be metadata-safe under partial/truncated event payloads
MSD aggregation and normalization logic SHALL process event records without assuming metadata and record rows share the same container map structure.

#### Scenario: Truncated upstream/downstream events do not break aggregation
- **WHEN** upstream or downstream event fetch returns non-complete quality metadata
- **THEN** MSD aggregation pipeline SHALL continue with available records
- **THEN** pipeline SHALL not raise type/iteration errors due to metadata entries

#### Scenario: Metadata-agnostic normalizers
- **WHEN** event payload includes metadata side-channel fields
- **THEN** MSD record normalizers SHALL only iterate over validated record collections
- **THEN** non-record metadata fields SHALL be ignored by row normalizers

### Requirement: MSD API response SHALL surface data completeness state
MSD-related API responses built from staged events SHALL expose query quality metadata to callers.

#### Scenario: Partial MSD aggregation response
- **WHEN** one or more staged event domains are partial or truncated
- **THEN** MSD response SHALL include `quality_meta.status` with non-complete value
- **THEN** response SHALL include affected domain details for operator diagnostics

#### Scenario: Complete MSD aggregation response
- **WHEN** all contributing staged domains are complete
- **THEN** MSD response SHALL include `quality_meta.status = "complete"`
