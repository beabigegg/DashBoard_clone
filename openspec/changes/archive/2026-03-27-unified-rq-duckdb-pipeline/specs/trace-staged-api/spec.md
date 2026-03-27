## MODIFIED Requirements

### Requirement: Staged trace API SHALL prefer the spool-safe async path for heavy events work
`POST /api/trace/events` SHALL prefer RQ + spool execution for heavy work, while preserving compatibility for cache hits and migrated consumers.

#### Scenario: Existing spool available
- **WHEN** the events request matches a valid spool / completed async result
- **THEN** the endpoint SHALL return results without rerunning Oracle work

#### Scenario: No spool available
- **WHEN** the events request has no reusable spool
- **THEN** the endpoint SHALL enqueue the events work to RQ and return HTTP 202 for the async-capable path

### Requirement: MSD aggregation SHALL be computed from spool-backed runtime
For `profile=mid_section_defect`, events aggregation SHALL be computed from spool-backed DuckDB/runtime logic instead of large in-memory pandas aggregation.

#### Scenario: MSD aggregation runs from staged dataset
- **WHEN** `POST /api/trace/events` is called with `profile=mid_section_defect`
- **THEN** the aggregation stage SHALL read from the staged trace dataset / runtime view instead of materializing a large pandas frame in the web worker
- **THEN** any downstream detail or export flow SHALL be able to reference the same canonical staged dataset identity

### Requirement: Guard retirement SHALL be gated by path retirement
CID limits and sync RSS rejection on trace events SHALL only be removed once all relevant heavy execution is guaranteed to go through the spool-safe path.

#### Scenario: Legacy sync path still exists
- **WHEN** a sync compatibility path remains
- **THEN** protection guards SHALL remain in place for that path

#### Scenario: Sync path retired
- **WHEN** all heavy trace events execution is routed through RQ/spool
- **THEN** the legacy CID and RSS guards MAY be removed
