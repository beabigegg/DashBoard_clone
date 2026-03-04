## ADDED Requirements

### Requirement: Reject History cache-SQL runtime SHALL execute against cached datasets without full DataFrame materialization
The system SHALL provide a SQL runtime for reject-history cached queries that reads from cache/spool data sources and avoids requiring full pandas DataFrame materialization as the primary execution path.

#### Scenario: Spool-backed execution
- **WHEN** a valid `query_id` has parquet spool metadata available
- **THEN** the runtime SHALL execute SQL directly against the spool dataset
- **THEN** the request SHALL NOT require loading the entire dataset into a pandas DataFrame before filtering and aggregation

#### Scenario: Source resolution fallback
- **WHEN** spool data is unavailable for a valid `query_id`
- **THEN** the runtime SHALL follow a deterministic fallback order configured by system policy
- **THEN** the fallback decision SHALL be observable via telemetry metadata

### Requirement: Reject History cache-SQL runtime SHALL preserve filter semantics across batch/view/export paths
The runtime SHALL apply policy, supplementary, trend-date, and pareto selection filters with the same business semantics used by existing reject-history APIs.

#### Scenario: Batch pareto filter parity
- **WHEN** `batch-pareto` is requested with policy toggles, supplementary filters, trend dates, and `sel_*` selections
- **THEN** SQL runtime output SHALL preserve exclude-self cross-filter semantics for each dimension
- **THEN** `pareto_scope=top80` and `pareto_display_scope=top20` behavior SHALL remain unchanged

#### Scenario: View filter parity
- **WHEN** `view` is requested with `query_id` and active supplementary/interactive filters
- **THEN** `summary`, `trend`, and paginated `detail` SHALL all reflect the same effective filter set
- **THEN** response schema SHALL remain compatible with existing frontend contracts

#### Scenario: Export filter parity
- **WHEN** `export-cached` is requested with the same filters as `view`
- **THEN** exported rows SHALL represent the same filtered data scope as view/detail
- **THEN** column naming and field semantics SHALL remain unchanged

### Requirement: Reject History cache-SQL runtime SHALL support controlled rollout and safe fallback
The system SHALL expose runtime switches to enable or disable SQL execution per endpoint and SHALL support fallback to legacy computation when SQL runtime is unavailable.

#### Scenario: Endpoint-level enablement
- **WHEN** SQL runtime is enabled only for `batch-pareto`
- **THEN** `batch-pareto` SHALL use SQL runtime
- **THEN** `view` and `export-cached` SHALL continue using legacy path until explicitly enabled

#### Scenario: SQL runtime fallback
- **WHEN** SQL runtime encounters an execution failure for a request
- **THEN** the system SHALL apply configured fallback behavior (legacy path or fail-fast)
- **THEN** the response or metadata SHALL include a deterministic fallback reason code for operations troubleshooting
