## ADDED Requirements

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

## REMOVED Requirements

### Requirement: Pareto materialization telemetry display
**Reason**: The Pareto materialization feature has been fully superseded by DuckDB cache-sql (`reject_cache_sql_runtime`). Both feature flags (`PARETO_MATERIALIZATION_ENABLED`, `PARETO_MATERIALIZATION_READ_ENABLED`) have never been enabled. The panel displays all zeros, misleading operators.
**Migration**: No migration needed. The underlying `reject_pareto_materialized.py` module remains in the codebase for the runtime fallback chain; only the admin dashboard telemetry display is removed.
