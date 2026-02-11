## Purpose
Define stable requirements for vue-vite-page-architecture.

## Requirements


### Requirement: Pure Vite pages SHALL be served as static HTML
The system SHALL support serving Vite-built HTML pages directly via Flask without Jinja2 rendering.

#### Scenario: Serve pure Vite page
- **WHEN** user navigates to a pure Vite page route (e.g., `/qc-gate`)
- **THEN** Flask SHALL serve the pre-built HTML file from `static/dist/` via `send_from_directory`
- **THEN** the HTML SHALL NOT pass through Jinja2 template rendering

#### Scenario: Page works as top-level navigation target
- **WHEN** a pure Vite page is opened from portal direct navigation
- **THEN** the page SHALL render correctly as a top-level route without iframe embedding dependency
- **THEN** page functionality SHALL NOT rely on portal-managed frame lifecycle

### Requirement: Vite config SHALL support Vue SFC and HTML entry points
The Vite build configuration SHALL support Vue Single File Components alongside existing vanilla JS entries.

#### Scenario: Vue plugin coexistence
- **WHEN** `vite build` is executed
- **THEN** Vue SFC (`.vue` files) SHALL be compiled by `@vitejs/plugin-vue`
- **THEN** existing vanilla JS entry points SHALL continue to build without modification

#### Scenario: HTML entry point
- **WHEN** a page uses an HTML file as its Vite entry point
- **THEN** Vite SHALL process the HTML and its referenced JS/CSS into `static/dist/`
- **THEN** the output SHALL include `<page-name>.html`, `<page-name>.js`, and `<page-name>.css`

#### Scenario: Chunk splitting
- **WHEN** Vite builds the project
- **THEN** Vue runtime SHALL be split into a `vendor-vue` chunk
- **THEN** ECharts modules (including TreemapChart, BarChart, LineChart) SHALL be split into the existing `vendor-echarts` chunk
- **THEN** chunk splitting SHALL NOT affect existing page bundles

#### Scenario: Migrated page entry replacement
- **WHEN** a vanilla JS page is migrated to Vue 3
- **THEN** its Vite entry SHALL change from JS file to HTML file (e.g., `src/wip-overview/main.js` → `src/wip-overview/index.html`)
- **THEN** the original JS entry SHALL be replaced, not kept alongside

#### Scenario: Hold Overview entry point
- **WHEN** the hold-overview page is added
- **THEN** `vite.config.js` input SHALL include `'hold-overview': resolve(__dirname, 'src/hold-overview/index.html')`
- **THEN** the build SHALL produce `hold-overview.html`, `hold-overview.js`, and `hold-overview.css` in `static/dist/`

#### Scenario: Hold History entry point
- **WHEN** the hold-history page is added
- **THEN** `vite.config.js` input SHALL include `'hold-history': resolve(__dirname, 'src/hold-history/index.html')`
- **THEN** the build SHALL produce `hold-history.html`, `hold-history.js`, and `hold-history.css` in `static/dist/`

#### Scenario: Shared CSS import across migrated pages
- **WHEN** multiple migrated pages import a shared CSS module (e.g., `wip-shared/styles.css`)
- **THEN** Vite SHALL bundle the shared CSS into each page's output CSS
- **THEN** shared CSS SHALL NOT create a separate shared chunk that requires additional HTTP requests

#### Scenario: Shared composable import across module boundaries
- **WHEN** a migrated page imports a composable from another shared module (e.g., `hold-history` imports `useAutoRefresh` from `wip-shared/`)
- **THEN** the composable SHALL be bundled into the importing page's JS output
- **THEN** cross-module imports SHALL NOT create unexpected shared chunks

### Requirement: Pure Vite pages SHALL handle API calls without legacy MesApi
Pure Vite pages SHALL use the existing `frontend/src/core/api.js` module for API communication without depending on the global `window.MesApi` object from `_base.html`.

#### Scenario: API GET request from pure Vite page
- **WHEN** a pure Vite page makes a GET API call
- **THEN** the call SHALL use the `apiGet` function from `core/api.js`
- **THEN** the call SHALL work without `window.MesApi` being present

### Requirement: Pure Vite pages SHALL handle POST API calls without legacy MesApi
Pure Vite pages SHALL use the `apiPost` function from `core/api.js` for POST requests without depending on `window.MesApi`.

#### Scenario: API POST request from pure Vite page
- **WHEN** a pure Vite page makes a POST API call
- **THEN** the call SHALL use the `apiPost` function from `core/api.js`
- **THEN** the call SHALL include `Content-Type: application/json` header
- **THEN** the call SHALL work without `window.MesApi` being present

#### Scenario: CSRF token handling in POST requests
- **WHEN** a pure Vite page calls `apiPost`
- **THEN** `apiPost` SHALL attempt to read CSRF token from `<meta name="csrf-token">`
- **THEN** if no meta tag exists, the request SHALL still proceed (non-admin APIs do not enforce CSRF)

### Requirement: Pure Vite pages with server-side route validation SHALL use send_from_directory with pre-validation
Pages that require server-side parameter validation before serving SHALL validate parameters in the Flask route and then serve the static HTML.

#### Scenario: Hold Detail reason validation
- **WHEN** user navigates to `/hold-detail` without a `reason` parameter
- **THEN** Flask SHALL redirect to `/wip-overview`
- **WHEN** user navigates to `/hold-detail?reason={value}`
- **THEN** Flask SHALL serve the pre-built HTML file from `static/dist/` via `send_from_directory`
- **THEN** the HTML SHALL NOT pass through Jinja2 template rendering

#### Scenario: Frontend fallback validation
- **WHEN** the pure Vite hold-detail page loads
- **THEN** the page SHALL read `reason` from URL parameters
- **THEN** if `reason` is empty or missing, the page SHALL redirect to `/wip-overview`

### Requirement: Mid-section defect page SHALL separate filter state from query state
The mid-section defect page SHALL maintain separate reactive state for UI input (`filters`) and committed query parameters (`committedFilters`).

#### Scenario: User changes date without clicking query
- **WHEN** user modifies the date range in the filter bar but does not click "查詢"
- **THEN** auto-refresh, pagination, and CSV export SHALL continue using the previously committed filter values
- **THEN** the new date range SHALL NOT affect any API calls until "查詢" is clicked

#### Scenario: User clicks query button
- **WHEN** user clicks "查詢"
- **THEN** the current `filters` state SHALL be snapshotted into `committedFilters`
- **THEN** all subsequent API calls SHALL use the committed values

#### Scenario: CSV export uses committed filters
- **WHEN** user clicks "匯出 CSV" after modifying filters without re-querying
- **THEN** the export SHALL use the committed filter values from the last query
- **THEN** the export SHALL NOT use the current UI filter values

### Requirement: Mid-section defect page SHALL cancel in-flight requests on new query
The mid-section defect page SHALL use `AbortController` to cancel in-flight API requests when a new query is initiated.

#### Scenario: New query cancels previous query
- **WHEN** user clicks "查詢" while a previous query is still in-flight
- **THEN** the previous query's summary and detail requests SHALL be aborted
- **THEN** the AbortError SHALL be handled silently (no error banner shown)

#### Scenario: Page navigation cancels previous detail request
- **WHEN** user clicks next page while a previous page request is still in-flight
- **THEN** the previous page request SHALL be aborted
- **THEN** the new page request SHALL proceed independently

#### Scenario: Query and pagination use independent abort keys
- **WHEN** a query is in-flight and user triggers pagination
- **THEN** the query SHALL NOT be cancelled by the pagination request
- **THEN** the pagination SHALL use a separate abort key from the query
