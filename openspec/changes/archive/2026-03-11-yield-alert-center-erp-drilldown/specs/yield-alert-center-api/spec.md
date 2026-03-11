## ADDED Requirements

### Requirement: Yield Alert Center API SHALL provide ERP-based yield aggregates
The API SHALL compute yield baseline metrics from `ERP_WIP_MOVETXN` and `ERP_WIP_MOVETXN_DETAIL` and expose consistent aggregate results for requested time windows and dimensions.

#### Scenario: Default aggregate query
- **WHEN** client requests yield summary without optional grouping
- **THEN** API SHALL return at least `transaction_qty`, `scrap_qty`, and `yield_pct`
- **THEN** `yield_pct` SHALL be computed from ERP quantities in the same response context

#### Scenario: Dimension aggregate query
- **WHEN** client requests grouping by supported dimensions (`department`, `line`, `package`, `type`, `function`, `operation`)
- **THEN** API SHALL return per-group aggregates using the requested dimension keys
- **THEN** API SHALL return totals that reconcile with ungrouped results for the same filters

### Requirement: Yield Alert Center API SHALL expose alert candidate records
The API SHALL output alert candidates based on configurable yield risk criteria using ERP aggregate windows.

#### Scenario: Alert candidate list
- **WHEN** client requests alert candidates for a valid time range
- **THEN** API SHALL return a paginated list including alert key fields (`date_bucket`, `workorder`, `reason_code`, `scrap_qty`, `yield_pct`, `risk_level`)
- **THEN** response SHALL include deterministic sorting and pagination metadata

#### Scenario: No alerts in range
- **WHEN** no records satisfy alert criteria for the requested range
- **THEN** API SHALL return success with an empty list
- **THEN** response SHALL include zero-count pagination metadata without error

### Requirement: Yield Alert Center API SHALL enforce query safety boundaries
The API SHALL prevent unbounded high-cardinality Oracle scans through explicit window limits and bounded response size.

#### Scenario: Exceeding time window policy
- **WHEN** client requests a date range larger than configured maximum window
- **THEN** API SHALL reject the request with a validation error
- **THEN** response SHALL include a machine-readable reason indicating time-window violation

#### Scenario: Page size guardrail
- **WHEN** client requests `per_page` above configured maximum
- **THEN** API SHALL cap or reject according to policy
- **THEN** response SHALL expose effective page size in pagination metadata

### Requirement: Yield Alert Center API SHALL support performance-aware result reuse
The API SHALL support cache-aware execution for repeated equivalent queries.

#### Scenario: Cache hit response
- **WHEN** the same normalized query parameters are requested within freshness window
- **THEN** API SHALL return cached aggregate/alert results
- **THEN** response metadata SHALL indicate cache hit status

#### Scenario: Cache miss response
- **WHEN** no reusable cache entry exists
- **THEN** API SHALL execute Oracle query path and return computed results
- **THEN** response metadata SHALL indicate cache miss status
