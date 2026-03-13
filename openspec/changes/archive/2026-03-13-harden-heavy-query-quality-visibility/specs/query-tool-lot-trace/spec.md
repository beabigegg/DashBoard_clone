## ADDED Requirements

### Requirement: Query-tool EventFetcher detail responses SHALL be single/batch parity-safe for completeness metadata
Query-tool detail APIs backed by EventFetcher SHALL return `quality_meta` consistently in both single-container and batch-container modes.

#### Scenario: Single-container history preserves quality metadata
- **WHEN** client calls `GET /api/query-tool/lot-history?container_id=<id>` and EventFetcher reports non-complete status
- **THEN** response payload SHALL include `quality_meta.status` and associated diagnostics (`reasons`, limits, failed ranges/domains when available)
- **THEN** metadata schema SHALL match batch history mode semantics

#### Scenario: Single-container association preserves quality metadata
- **WHEN** client calls `GET /api/query-tool/lot-associations?container_id=<id>&type=materials|rejects|holds` and EventFetcher reports non-complete status
- **THEN** response payload SHALL include `quality_meta.status` for the requested association tab
- **THEN** metadata schema SHALL match batch association mode semantics

### Requirement: Query-tool LOT detail UI SHALL render visible non-complete warnings in all detail modes
LOT detail warnings SHALL be driven by `quality_meta` regardless of whether data came from single or batch query mode.

#### Scenario: Warning in single-container mode
- **WHEN** active LOT detail sub-tab receives `quality_meta.status = "partial"` or `"truncated"`
- **THEN** UI SHALL display a visible warning banner/message before the table/timeline content
- **THEN** warning text SHALL indicate possible incompleteness risk

#### Scenario: Warning clear on complete status
- **WHEN** subsequent refresh for the same sub-tab returns `quality_meta.status = "complete"`
- **THEN** non-complete warning SHALL be cleared for that sub-tab
