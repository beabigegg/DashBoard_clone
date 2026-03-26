## ADDED Requirements

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
- **THEN** its Vite entry SHALL change from JS file to HTML file (e.g., `src/tables/main.js` → `src/tables/index.html`)
- **THEN** the original JS entry SHALL be replaced, not kept alongside
