## MODIFIED Requirements

### Requirement: Stress tests SHALL assert minimum thresholds
Each stress test SHALL assert that the endpoint meets minimum performance thresholds under concurrent load, including system resource thresholds when load monitoring is enabled.

#### Scenario: Success rate threshold
- **WHEN** a stress test runs with the configured number of concurrent users
- **THEN** the success rate SHALL be >= 95%

#### Scenario: Response time threshold
- **WHEN** a stress test runs with the configured number of concurrent users
- **THEN** the average response time SHALL be < 5 seconds

#### Scenario: System memory threshold under load
- **WHEN** a stress test runs with load monitoring enabled (`STRESS_LOAD_MONITORING=1`)
- **THEN** peak system memory usage SHALL be < 85% (configurable via `STRESS_MAX_MEM_PCT`, default 85)
- **THEN** if the threshold is exceeded, the test SHALL fail with an `AssertionError` identifying the metric

#### Scenario: DB connection pool threshold under load
- **WHEN** a stress test runs with load monitoring enabled and admin endpoint is accessible
- **THEN** peak DB connection pool utilization SHALL be < 90% (configurable via `STRESS_MAX_DB_POOL_PCT`, default 90)
- **THEN** if the threshold is exceeded, the test SHALL fail with an `AssertionError` identifying the metric

#### Scenario: Load monitoring disabled
- **WHEN** a stress test runs without load monitoring (`STRESS_LOAD_MONITORING` unset or `0`)
- **THEN** system resource threshold assertions SHALL be skipped
- **THEN** existing success rate and response time assertions SHALL still apply

#### Scenario: Chunk boundary probes included in stress suite
- **WHEN** the stress test suite runs
- **THEN** chunk boundary probes (`test_chunk_boundary.py`) SHALL execute as part of the suite
- **THEN** boundary violations (unexpected HTTP 500 instead of expected 413) SHALL cause test failure

#### Scenario: Telemetry counter diffs reported for heavy tests
- **WHEN** a stress test runs with load monitoring enabled
- **THEN** guard rejection and spillover event counts SHALL be reported in the test summary
- **THEN** unexpected guard rejections above a configurable threshold (`STRESS_MAX_GUARD_REJECTS`, default 5) SHALL cause a warning (not failure)

#### Scenario: Data integrity verification included in stress suite
- **WHEN** the stress test suite runs with `STRESS_LOAD_MONITORING=1`
- **THEN** data integrity probes (`test_data_integrity.py`) SHALL execute for each heavy-query service
- **THEN** row count mismatches exceeding `STRESS_ROW_COUNT_TOLERANCE_PCT` (default 0.1%) SHALL cause test failure
