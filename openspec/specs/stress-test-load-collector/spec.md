## Purpose

LoadCollector infrastructure that samples system metrics (CPU, memory, DB pool, RQ queue depth) during stress test execution via background polling of health and admin endpoints.

## Requirements

### Requirement: LoadCollector SHALL sample system metrics during stress test execution
A `LoadCollector` class in `tests/stress/load_collector.py` SHALL poll the target application's `/health` endpoint at a configurable interval to collect CPU, memory, and system pressure metrics in a background daemon thread.

#### Scenario: LoadCollector samples metrics during test
- **WHEN** a `LoadCollector` is started with `base_url` and `interval=2.0`
- **THEN** it SHALL spawn a daemon thread that polls `GET {base_url}/health` every 2 seconds
- **THEN** each sample SHALL record `timestamp`, `cpu_percent`, `memory_used_pct`, `memory_available_mb`, and `memory_pressure` from the response

#### Scenario: LoadCollector handles connection failure gracefully
- **WHEN** a poll request to `/health` fails (timeout, connection refused, non-200 status)
- **THEN** the collector SHALL record a `null` sample for that interval
- **THEN** the collector SHALL NOT raise an exception or stop sampling

#### Scenario: LoadCollector stops cleanly on context exit
- **WHEN** the `LoadCollector` context manager exits (normal or exception)
- **THEN** the sampling thread SHALL stop within one interval period
- **THEN** `collector.summary` SHALL be populated with a `LoadSummary` dataclass

### Requirement: LoadCollector SHALL optionally collect extended metrics from admin endpoint
When the `/admin/api/performance-detail` endpoint is accessible, the collector SHALL additionally sample DB connection pool utilization and process cache statistics.

#### Scenario: Admin endpoint available
- **WHEN** `GET {base_url}/admin/api/performance-detail` returns HTTP 200
- **THEN** each sample SHALL additionally record `db_pool_active`, `db_pool_size`, and `db_pool_utilization_pct`

#### Scenario: Admin endpoint unavailable
- **WHEN** `GET {base_url}/admin/api/performance-detail` returns non-200 or fails
- **THEN** extended metrics SHALL be recorded as `null` for that sample
- **THEN** core metrics from `/health` SHALL continue to be collected

#### Scenario: RQ queue depth collected from admin endpoint
- **WHEN** the admin endpoint is accessible
- **THEN** each sample SHALL additionally record per-queue depth for all 5 RQ queues: `trace-events`, `reject-query`, `msd-analysis`, `production-history-query`, `yield-alert-query`

### Requirement: LoadSummary SHALL compute aggregate statistics from samples
The `LoadSummary` dataclass SHALL compute peak, average, and sample count from collected metrics.

#### Scenario: Summary with valid samples
- **WHEN** the collector has gathered N valid samples (N > 0)
- **THEN** `LoadSummary` SHALL contain `peak_cpu_pct`, `avg_cpu_pct`, `peak_mem_pct`, `avg_mem_pct`, `peak_db_pool_pct` (if available), `peak_queue_depth` per RQ queue (if available), `sample_count`, `duration_sec`, and `null_sample_count`

#### Scenario: Summary with all null samples
- **WHEN** all poll attempts failed (N valid samples = 0)
- **THEN** `LoadSummary` SHALL have all numeric fields set to `None`
- **THEN** `sample_count` SHALL be 0 and `null_sample_count` SHALL equal total attempts

### Requirement: LoadSummary SHALL support threshold assertions
`LoadSummary` SHALL provide an `assert_within()` method that verifies peak metrics do not exceed caller-specified thresholds.

#### Scenario: All metrics within thresholds
- **WHEN** `assert_within(max_cpu_pct=90, max_mem_pct=85, max_db_pool_pct=90)` is called
- **THEN** if all peak values are at or below their thresholds, no exception SHALL be raised

#### Scenario: Memory threshold exceeded
- **WHEN** `peak_mem_pct` is 88 and `assert_within(max_mem_pct=85)` is called
- **THEN** an `AssertionError` SHALL be raised with a message including the metric name, actual value, and threshold

#### Scenario: Threshold assertion with unavailable metrics
- **WHEN** `assert_within(max_db_pool_pct=90)` is called but `peak_db_pool_pct` is `None`
- **THEN** the DB pool assertion SHALL be skipped (not fail)

### Requirement: Pytest fixtures SHALL provide LoadCollector instances
`tests/stress/conftest.py` SHALL provide fixtures for creating and using `LoadCollector` instances.

#### Scenario: load_collector_factory fixture
- **WHEN** a stress test requests the `load_collector_factory` fixture (session-scoped)
- **THEN** it SHALL receive a callable that creates `LoadCollector(base_url, interval)` instances

#### Scenario: load_collector fixture
- **WHEN** a stress test requests the `load_collector` fixture (function-scoped)
- **THEN** it SHALL receive a `LoadCollector` instance configured with `base_url` from session config and default interval from `STRESS_LOAD_INTERVAL` env var (default 2.0)
