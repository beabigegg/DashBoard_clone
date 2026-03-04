## MODIFIED Requirements

### Requirement: Cache Telemetry MUST be Queryable for Operations
The system MUST provide cache telemetry suitable for operations diagnostics, including materialized Pareto cache behavior for reject-history workloads.

#### Scenario: Telemetry inspection
- **WHEN** operators request deep health status
- **THEN** cache-related metrics/state SHALL be present and interpretable for troubleshooting

#### Scenario: Materialized Pareto telemetry visibility
- **WHEN** materialized Pareto cache is enabled
- **THEN** telemetry SHALL expose at least hit count/rate, miss count/rate, build count, build failure count, and fallback count
- **THEN** telemetry SHALL expose latest snapshot freshness indicators and aggregate payload size indicators

## ADDED Requirements

### Requirement: Pareto materialization fallback reasons SHALL be operationally classifiable
Telemetry MUST classify fallback outcomes with stable reason codes so repeated degradations can be monitored and alerted.

#### Scenario: Snapshot miss fallback reason
- **WHEN** request falls back because no snapshot exists
- **THEN** telemetry SHALL record a stable reason code for snapshot miss

#### Scenario: Snapshot stale fallback reason
- **WHEN** request falls back because snapshot fails freshness/version checks
- **THEN** telemetry SHALL record a stable reason code for stale/incompatible snapshot

#### Scenario: Build failure fallback reason
- **WHEN** request falls back because materialization build failed
- **THEN** telemetry SHALL record a stable reason code for build failure
