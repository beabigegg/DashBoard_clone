## MODIFIED Requirements

### Requirement: HealthStatus popup uses four-section layout
The HealthStatus popup SHALL be reorganized into four sections: Core Services, System Resources, Cache, and Background Services.

#### Scenario: Core Services section
- **WHEN** the HealthStatus popup is opened
- **THEN** the "核心服務" section SHALL display:
  - Oracle DB status with pool saturation percentage
  - Redis status
  - Circuit Breaker state (CLOSED/OPEN/HALF_OPEN)

#### Scenario: System Resources section
- **WHEN** the HealthStatus popup is opened
- **THEN** the "系統資源" section SHALL display:
  - System memory usage percentage with used/total MB
  - Online user count (from `/health` response `online_count`)

#### Scenario: Cache section
- **WHEN** the HealthStatus popup is opened
- **THEN** the "快取" section SHALL display:
  - WIP cache status and last sync time
  - Resource cache (設備主檔) loaded status and count
  - Route cache mode and L1/L2 hit rates
  - Workcenter mapping count (workcenters / groups)

#### Scenario: Background Services section
- **WHEN** the HealthStatus popup is opened
- **THEN** the "背景服務" section SHALL display:
  - RQ Workers status (busy/total) and queue depth
  - MySQL Sync (SyncWorker) running status and last sync time
  - Anomaly Scheduler running status and anomaly count

### Requirement: /health endpoint includes sync_worker status
The `/health` response SHALL include a `sync_worker` object with `running` (boolean) and `last_sync_at` (ISO datetime string or null).

#### Scenario: SyncWorker is running
- **GIVEN** SyncWorker daemon thread is alive and last synced at 15:20
- **WHEN** `/health` is called
- **THEN** response SHALL include `"sync_worker": { "running": true, "last_sync_at": "2026-03-26T15:20:00" }`

#### Scenario: SyncWorker is disabled
- **GIVEN** MYSQL_SYNC_ENABLED=false
- **WHEN** `/health` is called
- **THEN** response SHALL include `"sync_worker": { "running": false, "last_sync_at": null }`

### Requirement: /health endpoint includes anomaly_scheduler status
The `/health` response SHALL include an `anomaly_scheduler` object with `running` (boolean), `last_run` (ISO date string or null), and `anomaly_count` (integer).

#### Scenario: Scheduler has run today
- **GIVEN** anomaly scheduler ran at 08:00 and found 64 anomalies
- **WHEN** `/health` is called
- **THEN** response SHALL include `"anomaly_scheduler": { "running": true, "last_run": "2026-03-26", "anomaly_count": 64 }`

### Requirement: /health endpoint includes online_count
The `/health` response SHALL include an `online_count` integer field representing active sessions.

#### Scenario: Active users present
- **GIVEN** 12 users have active sessions
- **WHEN** `/health` is called
- **THEN** response SHALL include `"online_count": 12`

### Requirement: Admin OverviewTab displays background service status
The admin dashboard OverviewTab SHALL display SyncWorker and Anomaly Scheduler status alongside existing service indicators.

#### Scenario: All services healthy
- **WHEN** the admin views the OverviewTab
- **THEN** SyncWorker SHALL show with a green dot and last sync time
- **AND** Anomaly Scheduler SHALL show with a green dot and anomaly count

#### Scenario: SyncWorker disabled
- **WHEN** MYSQL_SYNC_ENABLED=false
- **THEN** SyncWorker SHALL show with a grey "未啟用" indicator
