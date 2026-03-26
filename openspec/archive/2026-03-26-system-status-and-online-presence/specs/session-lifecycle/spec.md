## NEW Requirements

### Requirement: Graceful shutdown closes all active sessions
The system SHALL close all active login sessions (where `logout_time IS NULL`) during application shutdown, using each session's `last_active` timestamp as the effective logout time.

#### Scenario: Normal server shutdown
- **GIVEN** there are 3 active sessions with `logout_time IS NULL`
- **WHEN** `_shutdown_runtime_resources()` is called (via atexit or SIGTERM)
- **THEN** all 3 sessions SHALL have `logout_time` set to their respective `last_active` values
- **AND** `duration_sec` SHALL be computed as `last_active - login_time` for each

#### Scenario: Session with NULL last_active
- **GIVEN** a session where `last_active IS NULL` (login but never heartbeated)
- **WHEN** shutdown cleanup runs
- **THEN** `logout_time` SHALL be set to `login_time`
- **AND** `duration_sec` SHALL be 0

### Requirement: duration_sec uses last_active instead of current time
The `close_session()` method SHALL compute `duration_sec` as `last_active - login_time` instead of `now - login_time`. If `last_active` is NULL, it SHALL fallback to `now - login_time`.

#### Scenario: Normal logout with heartbeat history
- **GIVEN** a session with `login_time = 09:00` and `last_active = 11:30`
- **WHEN** user logs out at 11:35
- **THEN** `duration_sec` SHALL be 9000 (2.5 hours, based on last_active)
- **AND** `logout_time` SHALL be the current time (11:35)

#### Scenario: Logout without any heartbeat
- **GIVEN** a session with `login_time = 09:00` and `last_active IS NULL`
- **WHEN** user logs out at 09:05
- **THEN** `duration_sec` SHALL be 300 (fallback to now - login_time)

### Requirement: SyncWorker orphan session cleanup
The SyncWorker SHALL, on each 10-minute cycle, scan for orphan sessions where `login_time < now - 8 hours AND logout_time IS NULL` and close them using `last_active` as logout time.

#### Scenario: Orphan session older than 8 hours
- **GIVEN** a session with `login_time` 10 hours ago, `last_active` 9.5 hours ago, `logout_time IS NULL`
- **WHEN** SyncWorker runs its cleanup cycle
- **THEN** the session SHALL be closed with `logout_time = last_active`
- **AND** `duration_sec` SHALL be 1800 (30 minutes of actual use)

#### Scenario: Active session within 8 hours
- **GIVEN** a session with `login_time` 2 hours ago, `logout_time IS NULL`
- **WHEN** SyncWorker runs its cleanup cycle
- **THEN** the session SHALL NOT be modified

### Requirement: MySQL historical data cleanup
On first SyncWorker startup after this change, the system SHALL truncate the `dashboard_login_sessions` MySQL table to remove historically inaccurate duration data. This SHALL be a one-time migration controlled by a version flag.

#### Scenario: First startup after migration
- **WHEN** SyncWorker starts and detects migration version < 2
- **THEN** it SHALL execute `TRUNCATE TABLE dashboard_login_sessions`
- **AND** set the migration version to 2

#### Scenario: Subsequent startups
- **WHEN** SyncWorker starts and migration version >= 2
- **THEN** it SHALL NOT truncate the table

### Requirement: LoginSessionStore.get_active_count()
A new method `get_active_count()` SHALL return the count of sessions where `logout_time IS NULL AND last_active >= now - 30 minutes`.

#### Scenario: Mixed session states
- **GIVEN** 5 sessions: 2 active (heartbeat within 30 min), 1 stale (heartbeat 2 hours ago, no logout), 2 logged out
- **WHEN** `get_active_count()` is called
- **THEN** it SHALL return 2

### Requirement: LoginSessionStore.close_all_active_sessions()
A new method `close_all_active_sessions()` SHALL close all sessions where `logout_time IS NULL`, setting `logout_time = last_active` (or `login_time` if `last_active IS NULL`) and computing `duration_sec` accordingly.

#### Scenario: Bulk close on shutdown
- **WHEN** `close_all_active_sessions()` is called
- **THEN** all sessions with `logout_time IS NULL` SHALL be updated
- **AND** `synced` SHALL be set to 0 for all affected rows (triggering re-sync to MySQL)
