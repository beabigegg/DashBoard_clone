## ADDED Requirements

### Requirement: Reject History API SHALL provide batch Pareto endpoint with cross-filter
The API SHALL provide a batch Pareto endpoint that returns all 6 dimension Pareto results in a single response, supporting cross-dimension filtering with exclude-self logic.

#### Scenario: Batch Pareto response structure
- **WHEN** `GET /api/reject-history/batch-pareto` is called with valid `query_id`
- **THEN** response SHALL be `{ success: true, data: { dimensions: { reason: {...}, package: {...}, type: {...}, workflow: {...}, workcenter: {...}, equipment: {...} } } }`
- **THEN** each dimension object SHALL include `items` array with same schema as reason-pareto items (`reason`, `metric_value`, `pct`, `cumPct`, `MOVEIN_QTY`, `REJECT_TOTAL_QTY`, `DEFECT_QTY`, `count`)

#### Scenario: Cross-filter exclude-self logic
- **WHEN** `sel_reason=A&sel_type=X` is provided
- **THEN** reason Pareto SHALL be computed with type=X filter applied (but NOT reason=A filter)
- **THEN** type Pareto SHALL be computed with reason=A filter applied (but NOT type=X filter)
- **THEN** package/workflow/workcenter/equipment Paretos SHALL be computed with both reason=A AND type=X filters applied

#### Scenario: Empty selections return unfiltered Paretos
- **WHEN** batch-pareto is called with no `sel_*` parameters
- **THEN** all 6 dimensions SHALL return their full Pareto distribution (same as calling reason-pareto individually with no cross-filter)

#### Scenario: Cache-only computation
- **WHEN** `query_id` does not exist in cache
- **THEN** the endpoint SHALL return HTTP 400 with error message indicating cache miss
- **THEN** the endpoint SHALL NOT fall back to Oracle query

#### Scenario: Supplementary and policy filters apply
- **WHEN** batch-pareto is called with supplementary filters (packages, workcenter_groups, reason) and policy toggles
- **THEN** all 6 dimension Paretos SHALL be computed after applying policy and supplementary filters first (before cross-filter)

#### Scenario: Data source is cached DataFrame only
- **WHEN** batch-pareto computes dimension Paretos
- **THEN** computation SHALL operate on the in-memory cached Pandas DataFrame (populated by the primary query)
- **THEN** the endpoint SHALL NOT issue any additional Oracle database queries
- **THEN** response time SHALL be sub-100ms since all computation is in-memory

#### Scenario: Display scope (TOP20) support
- **WHEN** `pareto_display_scope=top20` is provided
- **THEN** applicable dimensions (type, workflow, equipment) SHALL truncate results to top 20 items after sorting
- **WHEN** `pareto_display_scope` is omitted or `all`
- **THEN** all items SHALL be returned (subject to pareto_scope 80% filter if active)

### Requirement: Reject History API SHALL support multi-dimension Pareto selection in view and export
The detail view and export endpoints SHALL accept multiple dimension selections simultaneously and apply them with AND logic.

#### Scenario: Multi-dimension filter on view endpoint
- **WHEN** `GET /api/reject-history/view` is called with `sel_reason=A&sel_type=X`
- **THEN** returned rows SHALL match reason=A AND type=X (both filters applied simultaneously)

#### Scenario: Multi-dimension filter on export endpoint
- **WHEN** `GET /api/reject-history/export-cached` is called with `sel_reason=A&sel_type=X`
- **THEN** exported CSV SHALL contain only rows matching reason=A AND type=X

#### Scenario: Backward compatibility with single-dimension params
- **WHEN** `pareto_dimension` and `pareto_values` are provided (legacy format)
- **THEN** the API SHALL still accept and apply them as before
- **WHEN** both `sel_*` params and legacy params are provided
- **THEN** `sel_*` params SHALL take precedence

## MODIFIED Requirements

### Requirement: Reject History API SHALL provide reason Pareto endpoint
The API SHALL return sorted reason distribution data with cumulative percentages. The endpoint supports dimension selection via `dimension` parameter for single-dimension queries.

#### Scenario: Pareto response payload
- **WHEN** `GET /api/reject-history/reason-pareto` is called
- **THEN** each item SHALL include `reason`, `category`, selected metric value, `pct`, and `cumPct`
- **THEN** items SHALL be sorted descending by selected metric

#### Scenario: Metric mode validation
- **WHEN** `metric_mode` is provided
- **THEN** accepted values SHALL be `reject_total` or `defect`
- **THEN** invalid `metric_mode` SHALL return HTTP 400

#### Scenario: Dimension selection
- **WHEN** `dimension` parameter is provided with a valid value (reason, package, type, workflow, workcenter, equipment)
- **THEN** the endpoint SHALL return Pareto data for that dimension
- **WHEN** `dimension` is not provided
- **THEN** the endpoint SHALL default to `reason`
