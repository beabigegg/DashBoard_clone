## ADDED Requirements

### Requirement: Vue 3 SPA page replaces Jinja2 template
The `/admin/performance` route SHALL serve a Vue 3 SPA page built by Vite, replacing the existing Jinja2 server-rendered template. The SPA SHALL be registered as a Vite entry point and integrated into the portal-shell navigation as a `renderMode: 'native'` route.

#### Scenario: Page loads as Vue SPA
- **WHEN** user navigates to `/admin/performance`
- **THEN** the server SHALL return the Vite-built `admin-performance.html` static file (not a Jinja2 rendered template)

#### Scenario: Portal-shell integration
- **WHEN** the portal-shell renders `/admin/performance`
- **THEN** it SHALL load the page as a native Vue SPA (not an external iframe)

### Requirement: Status cards display system health
The dashboard SHALL display 4 status cards in a horizontal grid: Database, Redis, Circuit Breaker, and Worker PID. Each card SHALL show a StatusDot indicator (healthy/degraded/error/disabled) with the current status value.

#### Scenario: All systems healthy
- **WHEN** all backend systems report healthy status via `/admin/api/system-status`
- **THEN** all 4 status cards SHALL display green StatusDot indicators with their respective values

#### Scenario: Redis disabled
- **WHEN** Redis is disabled (`REDIS_ENABLED=false`)
- **THEN** the Redis status card SHALL display a disabled StatusDot indicator and the Redis cache panel SHALL show a graceful degradation message

### Requirement: Query performance panel with ECharts
The dashboard SHALL display query performance metrics (P50, P95, P99 latencies, total queries, slow queries) and an ECharts latency distribution chart, replacing the existing Chart.js implementation.

#### Scenario: Metrics loaded successfully
- **WHEN** `/admin/api/metrics` returns valid performance data
- **THEN** the panel SHALL display P50/P95/P99 latency values and render an ECharts bar chart showing latency distribution

#### Scenario: No metrics data
- **WHEN** `/admin/api/metrics` returns empty or null metrics
- **THEN** the panel SHALL display placeholder text indicating no data available

### Requirement: Redis cache detail panel
The dashboard SHALL display a Redis cache detail panel showing memory usage (as a GaugeBar), connected clients, hit rate percentage, peak memory, and a namespace key distribution table.

#### Scenario: Redis active with data
- **WHEN** `/admin/api/performance-detail` returns Redis data with namespace key counts
- **THEN** the panel SHALL display a memory GaugeBar, hit rate, client count, and a table listing each namespace with its key count

#### Scenario: Redis disabled
- **WHEN** Redis is disabled
- **THEN** the Redis detail panel SHALL display a disabled state message without errors

### Requirement: Memory cache panel
The dashboard SHALL display ProcessLevelCache statistics as grid cards (showing entries/max_size as a mini gauge and TTL) plus Route Cache telemetry (L1 hit rate, L2 hit rate, miss rate, total reads).

#### Scenario: Multiple caches registered
- **WHEN** `/admin/api/performance-detail` returns process_caches with multiple entries
- **THEN** the panel SHALL render one card per cache instance showing entries, max_size, TTL, and description

#### Scenario: Route cache telemetry
- **WHEN** `/admin/api/performance-detail` returns route_cache data
- **THEN** the panel SHALL display L1 hit rate, L2 hit rate, miss rate, and total reads

### Requirement: Connection pool panel
The dashboard SHALL display connection pool saturation as a GaugeBar and stat cards showing checked_out, checked_in, overflow, max_capacity, pool_size, pool_recycle, pool_timeout, and direct connection count.

#### Scenario: Pool under normal load
- **WHEN** pool saturation is below 80%
- **THEN** the GaugeBar SHALL display in a normal color (green/blue)

#### Scenario: Pool near saturation
- **WHEN** pool saturation exceeds 80%
- **THEN** the GaugeBar SHALL display in a warning color (yellow/orange/red)

### Requirement: Worker control panel
The dashboard SHALL display worker PID, uptime, cooldown status, and provide a restart button with a confirmation modal.

#### Scenario: Restart worker
- **WHEN** user clicks the restart button and confirms in the modal
- **THEN** the system SHALL POST to `/admin/api/worker/restart` and display the result

#### Scenario: Restart during cooldown
- **WHEN** worker is in cooldown period
- **THEN** the restart button SHALL be disabled with a cooldown indicator

### Requirement: System logs panel with filtering and pagination
The dashboard SHALL display system logs with level filtering, text search, and pagination controls.

#### Scenario: Filter by log level
- **WHEN** user selects a specific log level filter
- **THEN** only logs matching that level SHALL be displayed

#### Scenario: Paginate logs
- **WHEN** logs exceed the page size
- **THEN** pagination controls SHALL allow navigating between pages

### Requirement: Auto-refresh with toggle
The dashboard SHALL auto-refresh all panels every 30 seconds using `useAutoRefresh`. The user SHALL be able to toggle auto-refresh on/off and manually trigger a refresh.

#### Scenario: Auto-refresh enabled
- **WHEN** auto-refresh is enabled (default)
- **THEN** all panels SHALL refresh their data every 30 seconds via `Promise.all` parallel fetch

#### Scenario: Manual refresh
- **WHEN** user clicks the manual refresh button
- **THEN** all panels SHALL immediately refresh their data
