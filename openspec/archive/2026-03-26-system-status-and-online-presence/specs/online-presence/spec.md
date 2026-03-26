## NEW Requirements

### Requirement: Heartbeat response includes online_count
The `PATCH /api/auth/heartbeat` endpoint SHALL include `online_count` in its response payload, representing the current number of active users.

#### Scenario: Heartbeat with active users
- **GIVEN** 12 users have active sessions (heartbeat within 30 minutes)
- **WHEN** a user sends a heartbeat request
- **THEN** the response SHALL include `{ "online_count": 12 }` in addition to existing fields

### Requirement: Portal-shell header displays online count
The portal-shell header SHALL display the current online user count, updated via the heartbeat response (every 5 minutes).

#### Scenario: Online count display
- **GIVEN** the user is authenticated and heartbeat returns `online_count: 12`
- **THEN** the header SHALL display a user icon with the number "12" near the HealthStatus indicator
- **AND** the count SHALL update on each heartbeat cycle (every 5 minutes)

#### Scenario: Before first heartbeat
- **WHEN** the page first loads and no heartbeat has completed yet
- **THEN** the online count SHALL NOT be displayed (hidden, not "0")

### Requirement: useAuth composable exposes online count
The `useAuth.js` composable SHALL export a reactive `onlineCount` ref, updated from the heartbeat response.

#### Scenario: Reactive updates
- **WHEN** heartbeat response contains `online_count: 15`
- **THEN** `onlineCount.value` SHALL be updated to 15
- **AND** any component consuming `onlineCount` SHALL reactively update

### Requirement: Admin UsageTab online trend chart
The admin UsageTab SHALL display an online user count trend chart showing how the count changed over the selected time period.

#### Scenario: Trend data from metrics history
- **GIVEN** the metrics history contains online_count snapshots every 30 seconds
- **WHEN** the admin views the UsageTab
- **THEN** a trend chart SHALL display online_count over time
- **AND** the chart SHALL use the existing TrendChart component

### Requirement: Metrics history records online_count
The metrics history collector (30-second interval) SHALL include the current `online_count` in each snapshot, sourced from `LoginSessionStore.get_active_count()`.

#### Scenario: Snapshot includes online count
- **WHEN** the metrics history collector records a snapshot
- **THEN** the snapshot SHALL include an `online_count` field
- **AND** this field SHALL be synced to MySQL `dashboard_metrics_snapshots` table
