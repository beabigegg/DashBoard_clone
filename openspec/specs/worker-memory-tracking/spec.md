## ADDED Requirements

### Requirement: Metrics history SHALL record system memory in snapshots
The `MetricsHistoryCollector` SHALL include `system_mem_available_mb` and `system_mem_used_pct` in each 30-second snapshot using `psutil.virtual_memory()`.

#### Scenario: System memory recorded in snapshot
- **WHEN** the collector writes a snapshot and system has 16GB total with 4GB available
- **THEN** `system_mem_available_mb` SHALL be approximately 4096
- **THEN** `system_mem_used_pct` SHALL be approximately 75.0

#### Scenario: System memory collection failure
- **WHEN** `psutil.virtual_memory()` raises an exception during snapshot collection
- **THEN** the collector SHALL write NULL for both `system_mem_available_mb` and `system_mem_used_pct`
- **THEN** the collector SHALL continue collecting other metrics

## MODIFIED Requirements

### Requirement: Worker RSS memory in metrics history snapshots
The `MetricsHistoryCollector` SHALL include `worker_rss_bytes` in each 30-second snapshot, recording the current worker process peak RSS memory using Python's `resource.getrusage()`.

#### Scenario: RSS recorded in snapshot
- **WHEN** the collector writes a snapshot and the worker process has 256 MB peak RSS
- **THEN** the `worker_rss_bytes` column SHALL contain approximately 268435456

#### Scenario: RSS collection failure
- **WHEN** `resource.getrusage()` raises an exception
- **THEN** the collector SHALL write NULL for `worker_rss_bytes` and continue collecting other metrics

#### Scenario: Memory guard telemetry includes system memory
- **WHEN** `get_memory_guard_telemetry()` is called
- **THEN** the returned dict SHALL include `system_mem_used_pct` and `system_memory_pressure` fields in addition to existing per-worker fields
