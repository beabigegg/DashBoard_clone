## ADDED Requirements

### Requirement: Automatic archive log cleanup
The system SHALL provide a `cleanup_archive_logs()` function in `core/metrics_history.py` that deletes old rotated log files from `logs/archive/`, keeping the most recent N files per log type (access, error, watchdog, rq_worker, startup).

#### Scenario: Cleanup keeps recent files
- **WHEN** `cleanup_archive_logs()` is called with `keep_per_type=20` and there are 30 access_*.log files
- **THEN** 10 oldest access_*.log files SHALL be deleted, keeping the 20 most recent by modification time

#### Scenario: No excess files
- **WHEN** `cleanup_archive_logs()` is called and each type has fewer than `keep_per_type` files
- **THEN** no files SHALL be deleted

#### Scenario: Archive directory missing
- **WHEN** `cleanup_archive_logs()` is called and the archive directory does not exist
- **THEN** the function SHALL return 0 without error

### Requirement: Archive cleanup integrated into collector cycle
The `MetricsHistoryCollector` SHALL call `cleanup_archive_logs()` alongside the existing SQLite cleanup, running approximately every 50 minutes (every 100 collection intervals).

#### Scenario: Periodic cleanup executes
- **WHEN** the cleanup counter reaches 100 intervals
- **THEN** both SQLite metrics cleanup and archive log cleanup SHALL execute

### Requirement: Archive cleanup configuration
The archive log cleanup SHALL be configurable via environment variables: `ARCHIVE_LOG_DIR` (default: `logs/archive`) and `ARCHIVE_LOG_KEEP_COUNT` (default: 20).

#### Scenario: Custom keep count
- **WHEN** `ARCHIVE_LOG_KEEP_COUNT=10` is set
- **THEN** cleanup SHALL keep only the 10 most recent files per type
