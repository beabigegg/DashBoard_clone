## ADDED Requirements

### Requirement: SQLite metrics history store
The system SHALL provide a `MetricsHistoryStore` class in `core/metrics_history.py` that persists metrics snapshots to a SQLite database (`logs/metrics_history.sqlite` by default). The store SHALL use thread-local connections and a write lock, following the `LogStore` pattern in `core/log_store.py`.

#### Scenario: Write and query snapshots
- **WHEN** `write_snapshot(data)` is called with pool/redis/route_cache/latency metrics
- **THEN** a row SHALL be inserted into `metrics_snapshots` with the current ISO 8601 timestamp and worker PID

#### Scenario: Query by time range
- **WHEN** `query_snapshots(minutes=30)` is called
- **THEN** it SHALL return all rows from the last 30 minutes, ordered by timestamp ascending

#### Scenario: Retention cleanup
- **WHEN** `cleanup()` is called
- **THEN** rows older than `METRICS_HISTORY_RETENTION_DAYS` (default 3) SHALL be deleted, and total rows SHALL be capped at `METRICS_HISTORY_MAX_ROWS` (default 50000)

#### Scenario: Thread safety
- **WHEN** multiple threads write snapshots concurrently
- **THEN** the write lock SHALL serialize writes and prevent database corruption

### Requirement: Background metrics collector
The system SHALL provide a `MetricsHistoryCollector` class that runs a daemon thread collecting metrics snapshots at a configurable interval (default 30 seconds, via `METRICS_HISTORY_INTERVAL` env var).

#### Scenario: Automatic collection
- **WHEN** the collector is started via `start_metrics_history(app)`
- **THEN** it SHALL collect pool status, Redis info, route cache status, and query latency metrics every interval and write them to the store

#### Scenario: Graceful shutdown
- **WHEN** `stop_metrics_history()` is called
- **THEN** the collector thread SHALL stop within one interval period

#### Scenario: Subsystem unavailability
- **WHEN** a subsystem (e.g., Redis) is unavailable during collection
- **THEN** the collector SHALL write null/0 for those fields and continue collecting other metrics

### Requirement: Performance history API endpoint
The system SHALL expose `GET /admin/api/performance-history` that returns historical metrics snapshots.

#### Scenario: Query with time range
- **WHEN** the API is called with `?minutes=30`
- **THEN** it SHALL return `{"success": true, "data": {"snapshots": [...], "count": N}}`

#### Scenario: Time range bounds
- **WHEN** `minutes` is less than 1 or greater than 180
- **THEN** it SHALL be clamped to the range [1, 180]

#### Scenario: Admin authentication
- **WHEN** the API is called without admin authentication
- **THEN** it SHALL be rejected by the `@admin_required` decorator

### Requirement: Frontend trend charts
The system SHALL display 4 trend chart panels in the admin performance dashboard using vue-echarts VChart line/area charts.

#### Scenario: Trend charts with data
- **WHEN** historical snapshots contain more than 1 data point
- **THEN** the dashboard SHALL display trend charts for: connection pool saturation, query latency (P50/P95/P99), Redis memory, and cache hit rates

#### Scenario: Trend charts without data
- **WHEN** historical snapshots are empty or contain only 1 data point
- **THEN** the trend charts SHALL NOT be displayed (hidden via `v-if`)

#### Scenario: Auto-refresh
- **WHEN** the dashboard auto-refreshes
- **THEN** historical data SHALL also be refreshed alongside real-time metrics
