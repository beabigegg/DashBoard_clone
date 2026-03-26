## ADDED Requirements

### Requirement: Reject History Pareto materialization SHALL build reusable aggregate snapshots
The system SHALL build reusable Pareto aggregate snapshots from cached reject-history query datasets so interactive Pareto requests do not require full lot-level regrouping on every call.

#### Scenario: Build snapshot from cached dataset
- **WHEN** a valid `query_id` has cached reject-history dataset and Pareto data is requested
- **THEN** the system SHALL build a materialized snapshot containing the six supported Pareto dimensions (`reason`, `package`, `type`, `workflow`, `workcenter`, `equipment`)
- **THEN** the snapshot SHALL include quantities needed to compute `metric_value`, `pct`, `cumPct`, and affected count fields

#### Scenario: Build skipped for missing dataset cache
- **WHEN** the referenced `query_id` dataset is missing or expired
- **THEN** snapshot build SHALL NOT proceed
- **THEN** the caller SHALL receive a deterministic cache-miss outcome

### Requirement: Materialized snapshot keys SHALL encode filter identity and schema version
The system SHALL key materialized Pareto snapshots by canonical filter identity and schema version to prevent cross-context reuse.

#### Scenario: Distinct supplementary filters generate distinct snapshots
- **WHEN** two requests share the same `query_id` but differ in supplementary filters or policy toggles
- **THEN** they SHALL resolve to different materialized snapshot keys

#### Scenario: Schema version invalidates prior snapshots
- **WHEN** materialization schema version is incremented
- **THEN** snapshots produced by prior versions SHALL NOT be treated as valid hits

### Requirement: Materialized snapshots SHALL preserve cross-filter semantics
Materialized read paths SHALL produce the same cross-filter behavior as legacy DataFrame-based Pareto computation.

#### Scenario: Exclude-self behavior parity
- **WHEN** `sel_reason=A` and `sel_type=X` are active
- **THEN** reason Pareto SHALL be computed with `type=X` applied but without `reason=A` self-filter
- **THEN** type Pareto SHALL be computed with `reason=A` applied but without `type=X` self-filter

#### Scenario: Multi-dimension intersection parity
- **WHEN** multiple `sel_*` filters are active across dimensions
- **THEN** each non-excluded dimension result SHALL reflect the AND intersection of all other selected dimensions

### Requirement: Materialized snapshots SHALL enforce bounded lifecycle and capacity
Materialized Pareto cache storage SHALL be bounded by TTL and size guardrails to avoid unbounded memory growth.

#### Scenario: Snapshot expiry follows configured retention
- **WHEN** a materialized snapshot exceeds configured TTL
- **THEN** it SHALL be treated as expired and SHALL NOT be returned as a cache hit

#### Scenario: Oversized snapshot handling
- **WHEN** a snapshot build exceeds configured snapshot size guardrail
- **THEN** the snapshot SHALL be rejected or degraded according to policy
- **THEN** the system SHALL record the rejection/degradation reason for operations telemetry
