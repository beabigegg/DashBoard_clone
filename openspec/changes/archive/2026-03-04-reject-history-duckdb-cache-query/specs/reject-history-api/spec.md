## MODIFIED Requirements

### Requirement: Reject History API SHALL provide batch Pareto endpoint with cross-filter
The API SHALL provide a batch Pareto endpoint that returns all 6 dimension Pareto results in a single response, supporting cross-dimension filtering with exclude-self logic, and SHALL prefer materialized Pareto snapshots, then cache-SQL runtime, before considering legacy full-detail regrouping.

#### Scenario: Batch Pareto response structure
- **WHEN** `GET /api/reject-history/batch-pareto` is called with valid `query_id`
- **THEN** response SHALL be `{ success: true, data: { dimensions: { reason: {...}, package: {...}, type: {...}, workflow: {...}, workcenter: {...}, equipment: {...} } } }`
- **THEN** each dimension object SHALL include `items` array with schema (`reason`, `metric_value`, `pct`, `cumPct`, `MOVEIN_QTY`, `REJECT_TOTAL_QTY`, `DEFECT_QTY`, `count`)

#### Scenario: Cross-filter exclude-self logic
- **WHEN** `sel_reason=A&sel_type=X` is provided
- **THEN** reason Pareto SHALL be computed with type=X filter applied (but NOT reason=A filter)
- **THEN** type Pareto SHALL be computed with reason=A filter applied (but NOT type=X filter)
- **THEN** package/workflow/workcenter/equipment Paretos SHALL be computed with both reason=A AND type=X filters applied

#### Scenario: Empty selections return unfiltered Paretos
- **WHEN** batch-pareto is called with no `sel_*` parameters
- **THEN** all 6 dimensions SHALL return their full Pareto distribution (subject to `pareto_scope`)

#### Scenario: Cache-only computation
- **WHEN** `query_id` does not exist in cache
- **THEN** the endpoint SHALL return HTTP 400 with error message indicating cache miss
- **THEN** the endpoint SHALL NOT fall back to Oracle query

#### Scenario: Materialized snapshot preferred
- **WHEN** a valid and fresh materialized Pareto snapshot exists for the request context
- **THEN** the endpoint SHALL return results from that snapshot
- **THEN** the endpoint SHALL avoid full lot-level regrouping for the same request

#### Scenario: Materialized miss fallback behavior
- **WHEN** materialized snapshot is unavailable, stale, or build fails
- **THEN** the endpoint SHALL fall back to cache-SQL computation before legacy DataFrame computation
- **THEN** the response schema and filter semantics SHALL remain unchanged

#### Scenario: SQL fallback unavailable
- **WHEN** cache-SQL runtime is disabled or unavailable under materialized miss
- **THEN** the endpoint SHALL follow configured fallback policy deterministically
- **THEN** the response metadata SHALL expose the fallback reason code

#### Scenario: Supplementary and policy filters apply
- **WHEN** batch-pareto is called with supplementary filters (packages, workcenter_groups, reason) and policy toggles
- **THEN** all 6 dimension Paretos SHALL be computed after applying policy and supplementary filters first (before cross-filter)

#### Scenario: Display scope (TOP20) support
- **WHEN** `pareto_display_scope=top20` is provided
- **THEN** applicable dimensions (type, workflow, equipment) SHALL truncate results to top 20 items after sorting
- **WHEN** `pareto_display_scope` is omitted or `all`
- **THEN** all items SHALL be returned (subject to `pareto_scope` filter)

## ADDED Requirements

### Requirement: Reject History API SHALL provide SQL-first cache view derivation with schema parity
The API SHALL derive cache-backed `view` responses through SQL-first runtime when enabled, while preserving existing response schema and filter behavior.

#### Scenario: View response contract preserved
- **WHEN** `GET /api/reject-history/view` is called with valid `query_id`
- **THEN** response payload SHALL keep existing top-level structure containing `analytics_raw`, `summary`, and `detail`
- **THEN** pagination field names and types SHALL remain compatible with current frontend usage

#### Scenario: View SQL-first with deterministic fallback
- **WHEN** SQL runtime is enabled for `view`
- **THEN** summary/trend/detail derivation SHALL use SQL runtime as primary path
- **THEN** fallback to legacy path SHALL follow configured policy and preserve response schema

#### Scenario: Cache-expired behavior unchanged
- **WHEN** `query_id` cache has expired
- **THEN** endpoint SHALL return the same cache-expired status behavior as current implementation
