## ADDED Requirements

### Requirement: Unified Admin Dashboard SHALL provide tab-based navigation
The admin dashboard at `/admin/dashboard` SHALL present 6 tabs: Overview, Performance, Cache, Worker, Usage, Logs.

#### Scenario: Tab switching preserves state
- **WHEN** the user switches from Tab A to Tab B and back to Tab A
- **THEN** Tab A SHALL retain its previous state (scroll position, filter values, chart zoom)
- **THEN** this SHALL be implemented via `<KeepAlive>`

#### Scenario: Tab switching triggers refresh
- **WHEN** the user clicks a different tab
- **THEN** the newly active tab SHALL immediately call its `refresh()` method
- **THEN** the previous tab SHALL NOT be refreshed in the background

#### Scenario: Auto-refresh applies to active tab only
- **WHEN** auto-refresh is enabled (30s interval)
- **THEN** only the currently active tab's `refresh()` SHALL be called
- **THEN** non-active tabs SHALL retain their last-fetched data

### Requirement: Overview Tab SHALL display system health summary
The Overview tab SHALL aggregate data from `/health` and `/api/performance-history` into a single-screen health overview.

#### Scenario: Status cards display service health
- **WHEN** the Overview tab loads
- **THEN** it SHALL display 4 status cards: Database, Redis, Circuit Breaker, System Memory
- **THEN** each card SHALL show a StatusDot (healthy/degraded/unhealthy) and key metric

#### Scenario: Dead worker alert banner
- **WHEN** `/health` response contains `async_workers` with `rq_available === false` OR warnings include "RQ Worker 離線"
- **THEN** a warning banner SHALL be displayed prominently at the top of the Overview tab

#### Scenario: Mini trend charts
- **WHEN** performance history data is available
- **THEN** 4 mini TrendCharts SHALL be displayed: Latency P95, Pool Saturation, Worker Memory, Cache Hit Rate
- **THEN** each chart SHALL show the last 30 minutes of data

#### Scenario: Active alerts list
- **WHEN** `/health` response contains `warnings` array with entries
- **THEN** the Overview tab SHALL display each warning in an alerts panel

### Requirement: Admin Dashboard route SHALL be served by backend
The Flask backend SHALL serve the new SPA HTML at `/admin/dashboard`.

#### Scenario: Dashboard page route
- **GIVEN** `admin_routes.py` has `@admin_bp.route("/dashboard")`
- **WHEN** an admin user navigates to `/admin/dashboard`
- **THEN** the server SHALL return the `admin-dashboard.html` page with CSRF token injected

### Requirement: Vite build SHALL include admin-dashboard entry
The `vite.config.js` SHALL include `admin-dashboard` in its `rollupOptions.input`.

#### Scenario: Build produces admin-dashboard assets
- **WHEN** `npm run build` is executed
- **THEN** `admin-dashboard.js` and `admin-dashboard.css` SHALL be emitted to `static/dist/`
