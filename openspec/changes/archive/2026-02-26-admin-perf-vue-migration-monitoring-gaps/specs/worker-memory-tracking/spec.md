## ADDED Requirements

### Requirement: Worker RSS memory in metrics history snapshots
The `MetricsHistoryCollector` SHALL include `worker_rss_bytes` in each 30-second snapshot, recording the current worker process peak RSS memory using Python's `resource.getrusage()`.

#### Scenario: RSS recorded in snapshot
- **WHEN** the collector writes a snapshot and the worker process has 256 MB peak RSS
- **THEN** the `worker_rss_bytes` column SHALL contain approximately 268435456

#### Scenario: RSS collection failure
- **WHEN** `resource.getrusage()` raises an exception
- **THEN** the collector SHALL write NULL for `worker_rss_bytes` and continue collecting other metrics

### Requirement: Worker memory trend chart in Vue SPA
The admin performance Vue SPA SHALL display a "Worker 記憶體趨勢" TrendChart showing RSS memory over time in megabytes.

#### Scenario: Memory trend displayed
- **WHEN** historical snapshots contain `worker_rss_bytes` data with more than 1 data point
- **THEN** the dashboard SHALL display a TrendChart with RSS values converted to MB

#### Scenario: No memory data
- **WHEN** historical snapshots do not contain `worker_rss_bytes` data (all NULL)
- **THEN** the trend chart SHALL show "趨勢資料不足" message
