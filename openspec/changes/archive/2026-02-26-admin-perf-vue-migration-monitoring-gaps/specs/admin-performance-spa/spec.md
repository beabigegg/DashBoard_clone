## MODIFIED Requirements

### Requirement: Vue 3 SPA page replaces Jinja2 template
The `/admin/performance` route SHALL serve the Vite-built `admin-performance.html` static file directly. The Jinja2 template fallback SHALL be removed. If the SPA build artifact does not exist, the server SHALL return a standard HTTP error (no fallback rendering).

#### Scenario: Page loads as Vue SPA
- **WHEN** user navigates to `/admin/performance`
- **THEN** the server SHALL return the Vite-built `admin-performance.html` static file via `send_from_directory`

#### Scenario: Portal-shell integration
- **WHEN** the portal-shell renders `/admin/performance`
- **THEN** it SHALL load the page as a native Vue SPA (not an external iframe)

#### Scenario: Build artifact missing
- **WHEN** the SPA build artifact `admin-performance.html` does not exist in `static/dist/`
- **THEN** the server SHALL return an HTTP error (no Jinja2 fallback)

### Requirement: Connection pool panel
The dashboard SHALL display connection pool saturation as a GaugeBar and stat cards showing checked_out, checked_in, overflow, max_capacity, pool_size, pool_recycle, pool_timeout, direct connection count, slow_query_active, and slow_query_waiting.

#### Scenario: Pool under normal load
- **WHEN** pool saturation is below 80%
- **THEN** the GaugeBar SHALL display in a normal color (green/blue)

#### Scenario: Pool near saturation
- **WHEN** pool saturation exceeds 80%
- **THEN** the GaugeBar SHALL display in a warning color (yellow/orange/red)

#### Scenario: Slow query metrics displayed
- **WHEN** `db_pool.status` includes `slow_query_active` and `slow_query_waiting`
- **THEN** the panel SHALL display StatCards for both values

## REMOVED Requirements

### Requirement: Jinja2 template fallback for performance page
**Reason**: The Vue SPA is the sole UI. Maintaining a 1249-line Jinja template as fallback adds maintenance burden and feature divergence.
**Migration**: Delete `templates/admin/performance.html`. The route handler serves the SPA directly.
