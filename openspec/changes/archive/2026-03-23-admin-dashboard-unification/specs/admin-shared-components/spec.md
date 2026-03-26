## ADDED Requirements

### Requirement: Admin shared component library SHALL exist at admin-shared/
A shared component directory `frontend/src/admin-shared/components/` SHALL provide reusable admin-specific Vue components.

#### Scenario: StatusDot component is shared
- **GIVEN** `admin-shared/components/StatusDot.vue` exists
- **THEN** both `admin-dashboard` and `admin-performance` SHALL import from `admin-shared`
- **THEN** `admin-performance/components/StatusDot.vue` SHALL re-export from `admin-shared` for backward compatibility

#### Scenario: StatCard component is shared
- **GIVEN** `admin-shared/components/StatCard.vue` exists
- **THEN** both `admin-dashboard` and `admin-performance` SHALL import from `admin-shared`

#### Scenario: GaugeBar component is shared
- **GIVEN** `admin-shared/components/GaugeBar.vue` exists
- **THEN** both `admin-dashboard` and `admin-performance` SHALL import from `admin-shared`

#### Scenario: TrendChart component is shared
- **GIVEN** `admin-shared/components/TrendChart.vue` exists
- **THEN** both `admin-dashboard` and `admin-performance` SHALL import from `admin-shared`

### Requirement: useAdminData composable SHALL centralize API calls
A composable `admin-shared/composables/useAdminData.js` SHALL provide reactive data fetching for all admin API endpoints.

#### Scenario: Each data hook returns standard shape
- **WHEN** any `use*()` hook is called (e.g., `useSystemStatus()`)
- **THEN** it SHALL return `{ data, loading, error, refresh }` where:
  - `data` is a reactive ref with the API response (or null)
  - `loading` is a reactive boolean
  - `error` is a reactive string (or empty)
  - `refresh` is an async function to re-fetch

#### Scenario: useHealthSummary fetches from /health
- **WHEN** `useHealthSummary()` is used
- **THEN** it SHALL call `fetch('/health')` (not `/admin/api/...` since health is unauthed)
- **THEN** it SHALL parse status, services, warnings, async_workers, system_memory

### Requirement: Old admin SPAs SHALL remain functional via re-exports
The existing `admin-performance` and `admin-user-usage-kpi` SPAs SHALL continue to work after component extraction.

#### Scenario: admin-performance backward compatibility
- **WHEN** `admin-performance/App.vue` imports `./components/StatusDot.vue`
- **THEN** the import SHALL resolve to the `admin-shared` version via re-export
- **THEN** the existing `/admin/performance` page SHALL render identically
