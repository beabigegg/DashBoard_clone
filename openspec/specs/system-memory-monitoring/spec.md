## ADDED Requirements

### Requirement: Health endpoint SHALL report system memory status
The `/health` and `/health/deep` endpoints SHALL include a `system_memory` section with total, available, and usage percentage from `psutil.virtual_memory()`.

#### Scenario: System memory reported in health response
- **WHEN** `GET /health` is called
- **THEN** the response SHALL include `system_memory.total_mb`, `system_memory.available_mb`, `system_memory.used_pct`
- **THEN** `system_memory.pressure` SHALL be `"critical"` if `used_pct > 90`, `"high"` if `used_pct > 80`, otherwise `"normal"`

#### Scenario: psutil unavailable
- **WHEN** `psutil.virtual_memory()` raises an exception
- **THEN** the `system_memory` section SHALL contain `"error": "<message>"`
- **THEN** the health endpoint SHALL NOT fail entirely

### Requirement: Worker memory guard SHALL check system memory pressure
The `worker_memory_guard` background thread SHALL check `psutil.virtual_memory().percent` alongside per-worker RSS in each 15-second cycle.

#### Scenario: System memory above warn threshold
- **WHEN** `psutil.virtual_memory().percent` exceeds `SYSTEM_MEM_WARN_PCT` (default 85)
- **THEN** the guard SHALL log a warning with current system memory usage
- **THEN** the guard SHALL trigger cache eviction (same as existing RSS evict level)

#### Scenario: System memory above reject threshold
- **WHEN** `psutil.virtual_memory().percent` exceeds `SYSTEM_MEM_REJECT_PCT` (default 92)
- **THEN** the guard SHALL set an internal flag `system_memory_pressure=True`
- **THEN** the flag SHALL be readable via `get_memory_guard_telemetry()`

#### Scenario: System memory below reject threshold
- **WHEN** `psutil.virtual_memory().percent` drops below `SYSTEM_MEM_REJECT_PCT`
- **THEN** the guard SHALL clear the `system_memory_pressure` flag

#### Scenario: Heavy query rejection on system memory pressure
- **WHEN** `system_memory_pressure=True` and a new heavy query is submitted
- **THEN** the query route handler SHALL return HTTP 503 with `error` indicating system memory pressure and `retry_after=30`

### Requirement: Metrics history SHALL record system memory
The `MetricsHistoryCollector` SHALL include `system_mem_available_mb` and `system_mem_used_pct` in each 30-second snapshot.

#### Scenario: System memory recorded in snapshot
- **WHEN** the collector writes a snapshot and system has 16GB total with 4GB available
- **THEN** `system_mem_available_mb` SHALL be approximately 4096
- **THEN** `system_mem_used_pct` SHALL be approximately 75.0

#### Scenario: System memory collection failure
- **WHEN** `psutil.virtual_memory()` raises an exception during snapshot
- **THEN** the collector SHALL write NULL for both system memory columns and continue

### Requirement: Startup SHALL verify system memory sufficiency
The application startup (gunicorn `on_starting` hook or `start_server.sh`) SHALL verify that available system memory is sufficient for the target process count.

#### Scenario: Sufficient memory
- **WHEN** available system memory exceeds the estimated requirement (GUNICORN_WORKERS × 400MB + RQ workers × 200MB)
- **THEN** startup SHALL proceed normally with an info log

#### Scenario: Insufficient memory
- **WHEN** available system memory is below the estimated requirement
- **THEN** startup SHALL log a WARNING with the shortfall amount and a suggestion to reduce worker count
- **THEN** startup SHALL NOT be blocked (warning only)

### Requirement: Heavy-query memory guard telemetry SHALL be standardized across routes
All heavy-query endpoints SHALL emit standardized guard/fallback telemetry fields for overload diagnostics and cross-route comparison.

#### Scenario: Guard rejection telemetry
- **WHEN** a heavy-query request is rejected by memory guard
- **THEN** logs/metrics SHALL include route identifier, guard type, current RSS, configured threshold, and query scope identifiers
- **THEN** telemetry naming SHALL be consistent across query-tool, trace, reject-history, material-trace, and yield-alert routes

#### Scenario: Degraded fallback telemetry
- **WHEN** a heavy-query request is served via degraded fallback path (cache/spool/duckdb)
- **THEN** logs/metrics SHALL include fallback path type and success status
- **THEN** operators SHALL be able to compare `guard_reject` and `fallback_success` rates per route
