## ADDED Requirements

### Requirement: Materialized Pareto orchestration SHALL use cache-SQL fallback before legacy DataFrame regrouping
When materialized snapshots are not available, orchestration SHALL prefer cache-SQL runtime to compute batch Pareto results before attempting legacy DataFrame regrouping.

#### Scenario: Materialized miss uses cache-SQL fallback
- **WHEN** snapshot read misses, expires, or build fails for a batch-pareto request
- **THEN** orchestration SHALL invoke cache-SQL batch pareto computation as the first fallback path
- **THEN** returned payload SHALL preserve the same dimensions and item schema contract

#### Scenario: Cache-SQL unavailable fallback policy
- **WHEN** cache-SQL fallback is disabled or unavailable after materialized miss
- **THEN** orchestration SHALL apply configured fallback policy (legacy compute or fail-fast)
- **THEN** fallback reason SHALL be recorded in metadata for diagnostics

#### Scenario: Fallback path preserves cross-filter semantics
- **WHEN** cache-SQL fallback is used with multi-dimension `sel_*` filters
- **THEN** exclude-self cross-filter semantics SHALL remain equivalent to materialized and legacy behavior
- **THEN** `pareto_scope` and `pareto_display_scope` rules SHALL remain unchanged
