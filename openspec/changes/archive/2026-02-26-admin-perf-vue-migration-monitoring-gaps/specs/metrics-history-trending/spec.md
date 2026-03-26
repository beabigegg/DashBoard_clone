## MODIFIED Requirements

### Requirement: SQLite metrics history store
The system SHALL provide a `MetricsHistoryStore` class in `core/metrics_history.py` that persists metrics snapshots to a SQLite database (`logs/metrics_history.sqlite` by default). The store SHALL use thread-local connections and a write lock, following the `LogStore` pattern in `core/log_store.py`. The schema SHALL include columns for `slow_query_active` (INTEGER), `slow_query_waiting` (INTEGER), and `worker_rss_bytes` (INTEGER) in addition to the existing pool, Redis, route cache, and latency columns.

#### Scenario: Write and query snapshots
- **WHEN** `write_snapshot(data)` is called with pool/redis/route_cache/latency/slow_query/memory metrics
- **THEN** a row SHALL be inserted into `metrics_snapshots` with the current ISO 8601 timestamp, worker PID, and all metric columns

#### Scenario: Query by time range
- **WHEN** `query_snapshots(minutes=30)` is called
- **THEN** it SHALL return all rows from the last 30 minutes, ordered by timestamp ascending, including the new columns

#### Scenario: Retention cleanup
- **WHEN** `cleanup()` is called
- **THEN** rows older than `METRICS_HISTORY_RETENTION_DAYS` (default 3) SHALL be deleted, and total rows SHALL be capped at `METRICS_HISTORY_MAX_ROWS` (default 50000)

#### Scenario: Thread safety
- **WHEN** multiple threads write snapshots concurrently
- **THEN** the write lock SHALL serialize writes and prevent database corruption

#### Scenario: Schema migration for existing databases
- **WHEN** the store initializes on an existing database without the new columns
- **THEN** it SHALL execute ALTER TABLE ADD COLUMN for each missing column, tolerating "duplicate column" errors

### Requirement: Background metrics collector
The system SHALL provide a `MetricsHistoryCollector` class that runs a daemon thread collecting metrics snapshots at a configurable interval (default 30 seconds, via `METRICS_HISTORY_INTERVAL` env var). The collector SHALL include `slow_query_active`, `slow_query_waiting`, and `worker_rss_bytes` in each snapshot.

#### Scenario: Automatic collection
- **WHEN** the collector is started via `start_metrics_history(app)`
- **THEN** it SHALL collect pool status (including slow_query_active and slow_query_waiting), Redis info, route cache status, query latency metrics, and worker RSS memory every interval and write them to the store

#### Scenario: Graceful shutdown
- **WHEN** `stop_metrics_history()` is called
- **THEN** the collector thread SHALL stop within one interval period

#### Scenario: Subsystem unavailability
- **WHEN** a subsystem (e.g., Redis) is unavailable during collection
- **THEN** the collector SHALL write null/0 for those fields and continue collecting other metrics

### Requirement: Frontend trend charts
The system SHALL display 5 trend chart panels in the admin performance dashboard using vue-echarts VChart line/area charts: connection pool saturation, query latency (P50/P95/P99), Redis memory, cache hit rates, and worker memory.

#### Scenario: Trend charts with data
- **WHEN** historical snapshots contain more than 1 data point
- **THEN** the dashboard SHALL display trend charts for: connection pool saturation (including slow_query_active), query latency (P50/P95/P99), Redis memory, cache hit rates, and worker memory (RSS in MB)

#### Scenario: Trend charts without data
- **WHEN** historical snapshots are empty or contain only 1 data point
- **THEN** the trend charts SHALL NOT be displayed (hidden via `v-if`)

#### Scenario: Auto-refresh
- **WHEN** the dashboard auto-refreshes
- **THEN** historical data SHALL also be refreshed alongside real-time metrics
