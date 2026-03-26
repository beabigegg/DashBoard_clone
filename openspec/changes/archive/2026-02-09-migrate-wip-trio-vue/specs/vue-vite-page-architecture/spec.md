## MODIFIED Requirements

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
- **THEN** ECharts modules SHALL be split into the existing `vendor-echarts` chunk
- **THEN** chunk splitting SHALL NOT affect existing page bundles

#### Scenario: Migrated page entry replacement
- **WHEN** a vanilla JS page is migrated to Vue 3
- **THEN** its Vite entry SHALL change from JS file to HTML file (e.g., `src/wip-overview/main.js` → `src/wip-overview/index.html`)
- **THEN** the original JS entry SHALL be replaced, not kept alongside

#### Scenario: Shared CSS import across migrated pages
- **WHEN** multiple migrated pages import a shared CSS module (e.g., `wip-shared/styles.css`)
- **THEN** Vite SHALL bundle the shared CSS into each page's output CSS
- **THEN** shared CSS SHALL NOT create a separate shared chunk that requires additional HTTP requests

## ADDED Requirements

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
