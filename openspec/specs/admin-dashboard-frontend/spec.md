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

### Requirement: RQ Worker birth_date SHALL be serialized as UTC-aware ISO 8601
The backend `rq_monitor_service.get_rq_worker_details()` SHALL attach UTC timezone info to RQ Worker `birth_date` before serialization, producing ISO 8601 strings with `+00:00` suffix.

#### Scenario: birth_date includes timezone offset
- **WHEN** the admin dashboard API returns RQ worker details
- **THEN** each worker's `birth_date` field SHALL be an ISO 8601 string ending with `+00:00`
- **THEN** the string SHALL represent the same instant as the original UTC value from RQ

#### Scenario: Worker uptime displays correctly in UTC+8
- **WHEN** a worker was born at UTC 00:00 and current local time is UTC+8 08:00
- **THEN** the frontend `formatUptime()` SHALL display `0m` (not `8h`)

#### Scenario: Null birth_date handled gracefully
- **WHEN** a worker has no `birth_date` (null)
- **THEN** the API SHALL return `null` for `birth_date`
- **THEN** the frontend SHALL display `-` for uptime

### Requirement: worker_start_time SHALL be serialized as UTC-aware ISO 8601
The backend `admin_routes.api_worker_status()` SHALL use `datetime.fromtimestamp(ts, tz=timezone.utc)` to produce a timezone-aware datetime for `worker_start_time`.

#### Scenario: worker_start_time includes timezone offset
- **WHEN** the `/admin/api/worker/status` endpoint returns
- **THEN** `worker_start_time` SHALL be an ISO 8601 string ending with `+00:00`
- **THEN** the frontend `toLocaleString('zh-TW')` SHALL display the correct local time

### Requirement: Pareto materialization panel SHALL be removed from CacheTab
The CacheTab SHALL NOT display the Pareto materialization telemetry section (hit rate, build counts, fallback reasons), as the feature has been superseded by DuckDB cache-sql.

#### Scenario: CacheTab renders without Pareto section
- **WHEN** the CacheTab loads with valid performance detail data
- **THEN** the Pareto materialization SectionCard SHALL NOT be present in the DOM
- **THEN** all Pareto-related computed properties SHALL be removed from the component

#### Scenario: Backend omits pareto_materialization from performance detail
- **WHEN** `/admin/api/performance-detail` is called
- **THEN** the response SHALL NOT contain a `pareto_materialization` key

### Requirement: Admin Dashboard header SHALL use shared PageHeader component
The Admin Dashboard `App.vue` SHALL replace its custom `.dashboard-header` with the shared `PageHeader` component from `shared-ui/components/PageHeader.vue`.

#### Scenario: Header renders with PageHeader component
- **WHEN** the Admin Dashboard page loads
- **THEN** the header SHALL use the `header-gradient` class with 4-corner `border-radius: 12px`
- **THEN** the title SHALL display "Admin Dashboard" at `font-size: 24px`

#### Scenario: Auto-refresh and manual refresh remain functional
- **WHEN** the Admin Dashboard header renders with PageHeader
- **THEN** the auto-refresh toggle (checkbox + label) SHALL remain accessible
- **THEN** the manual refresh button SHALL trigger `refreshNow()`

#### Scenario: Tab navigation remains below header
- **WHEN** the Admin Dashboard renders
- **THEN** the tab bar SHALL appear below the PageHeader as an independent element
- **THEN** tab switching behavior SHALL be unchanged

### Requirement: Admin Dashboard container SHALL use 1800px max-width
The `.theme-admin-dashboard` container SHALL use `max-width: 1800px` to align with business page layout.

#### Scenario: Wide screen layout
- **WHEN** the viewport is wider than 1800px
- **THEN** the admin dashboard content SHALL be centered with `max-width: 1800px`

### Requirement: LogsTab SHALL be the single entry point for log viewing and persistent storage management
The Logs tab SHALL host all log-related views and cleanup actions in the admin dashboard, covering structured logs (SQLite + MySQL), SQLite databases under `logs/*.sqlite`, `.log` files under `logs/`, and rotated files under `logs/archive/`.

#### Scenario: Structured log section
- **WHEN** the user opens the Logs tab
- **THEN** the page SHALL render a "系統日誌" SectionCard that lists merged SQLite + MySQL log rows with level filter, search box, pagination, and a "清理日誌" button calling `POST /admin/api/logs/cleanup`

#### Scenario: SQLite databases section
- **WHEN** the user opens the Logs tab and `storage_info.sqlite_files` is non-empty
- **THEN** the page SHALL render a "SQLite 資料庫" SectionCard listing each sqlite file's path and size
- **AND** the row whose path includes `metrics_history` SHALL expose a "清除快照" button calling `POST /admin/api/performance-history/purge`

#### Scenario: Log files section
- **WHEN** the user opens the Logs tab and `storage_info.log_files` is non-empty
- **THEN** the page SHALL render a "Log 檔案" SectionCard listing each file's path and size
- **AND** SHALL provide a "清空 Log 檔案" button that calls `POST /admin/api/log-files/cleanup` with `{ "targets": ["logs"] }`

#### Scenario: Archive files section
- **WHEN** the user opens the Logs tab and `storage_info.archive_files` is non-empty
- **THEN** the page SHALL render an "Archive 歷史檔" SectionCard listing each archived file's path and size
- **AND** SHALL provide a "清空 Archive" button that calls `POST /admin/api/log-files/cleanup` with `{ "targets": ["archive"] }`

### Requirement: WorkerTab SHALL NOT manage any persistent storage
The Worker tab SHALL NOT display `.log` file listings, archive file listings, SQLite database listings, or any cleanup/purge buttons for storage under `logs/`. All persistent storage management SHALL live in the Logs tab.

#### Scenario: Worker tab no longer lists storage
- **WHEN** the user opens the Worker tab
- **THEN** no `Log 檔案`, `Archive`, `效能快照儲存`, or `SQLite` DataTable SHALL be rendered
- **AND** no "清空 Log 檔案", "清空 Archive", "清除快照", or "全部清理" button SHALL be present

### Requirement: Backend log API SHALL serialize timestamps as UTC ISO 8601
All `timestamp` fields returned by `GET /admin/api/logs` (from both SQLite and MySQL sources) SHALL be ISO 8601 strings with explicit `+00:00` UTC offset, regardless of original storage format.

#### Scenario: SQLite-sourced row carries UTC offset
- **WHEN** a log row was written by `core/log_store.write_log()` after this change ships
- **THEN** the `timestamp` SHALL match the regex `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?\+00:00$`

#### Scenario: Legacy naive SQLite row is normalized on read
- **WHEN** a pre-existing log row in `admin_logs.sqlite` has a naive ISO timestamp without timezone info
- **THEN** `GET /admin/api/logs` SHALL interpret it as the server's local timezone, convert it to UTC, and return it with `+00:00` suffix
- **AND** the original row in SQLite SHALL NOT be rewritten

#### Scenario: MySQL-sourced row is normalized
- **WHEN** a row from `dashboard_logs` is included in the merged response
- **THEN** its `timestamp` SHALL be returned as the same `+00:00` ISO 8601 format as SQLite rows

### Requirement: Backend log API SHALL sort merged rows by parsed datetime
`GET /admin/api/logs` SHALL sort merged SQLite + MySQL rows by parsing each `timestamp` into a `datetime` object before comparison, producing a strictly time-descending order even when the two sources had different stored string formats.

#### Scenario: Same-minute rows from both sources interleave correctly
- **GIVEN** a SQLite row at `2026-04-13T03:48:30+00:00` and a MySQL row at `2026-04-13T03:48:45+00:00`
- **WHEN** `GET /admin/api/logs` returns the merged page
- **THEN** the MySQL row SHALL appear before the SQLite row in the response

#### Scenario: Unparseable timestamps fall to the bottom
- **WHEN** a row's timestamp cannot be parsed by `datetime.fromisoformat`
- **THEN** it SHALL be ordered after all parseable rows rather than crashing the endpoint

### Requirement: Frontend SHALL use a shared formatter for log timestamps
The admin dashboard frontend SHALL provide a single shared utility `formatLogTime(iso)` exported from `frontend/src/core/datetime.js`, and LogsTab and WorkerTab SHALL both use it for any timestamp originating from the log/worker APIs.

#### Scenario: LogsTab uses shared formatter
- **WHEN** LogsTab renders a row from `GET /admin/api/logs`
- **THEN** the `timestamp` cell SHALL display the result of `formatLogTime(row.timestamp)`
- **AND** the displayed format SHALL be `YYYY/MM/DD HH:mm:ss` in the user's local timezone using `zh-TW` locale and 24-hour clock

#### Scenario: WorkerTab uses shared formatter for start time
- **WHEN** WorkerTab renders the worker start time card
- **THEN** the value SHALL be `formatLogTime(workerData.worker_start_time)` instead of an inline `toLocaleString` call

#### Scenario: Invalid input falls back gracefully
- **WHEN** `formatLogTime` is called with `null`, `undefined`, or a non-parseable string
- **THEN** it SHALL return `'-'` (or the original input if non-empty) without throwing

## REMOVED Requirements

### Requirement: Pareto materialization telemetry display
**Reason**: The Pareto materialization feature has been fully superseded by DuckDB cache-sql (`reject_cache_sql_runtime`). Both feature flags (`PARETO_MATERIALIZATION_ENABLED`, `PARETO_MATERIALIZATION_READ_ENABLED`) have never been enabled. The panel displays all zeros, misleading operators.
**Migration**: No migration needed. The underlying `reject_pareto_materialized.py` module remains in the codebase for the runtime fallback chain; only the admin dashboard telemetry display is removed.
