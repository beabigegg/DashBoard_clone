## ADDED Requirements

### Requirement: Hold detail back navigation uses SPA routing
The hold-detail page back button SHALL navigate to hold-overview using the portal-shell SPA router bridge when running inside portal-shell, without causing a full page reload.

#### Scenario: Back to hold-overview in portal-shell
- **WHEN** user clicks the "← Hold Overview" button on the hold-detail page within portal-shell
- **THEN** the portal-shell navigates to `/hold-overview` via `navigateToRuntimeRoute` without a full page reload, and the hold-overview page renders correctly

#### Scenario: Back to hold-overview in standalone mode
- **WHEN** user clicks the "← Hold Overview" button on the hold-detail page in standalone mode (no portal-shell)
- **THEN** the browser navigates to `/hold-overview` via `window.location.href` fallback

#### Scenario: Right-click open in new tab preserved
- **WHEN** user right-clicks the "← Hold Overview" button
- **THEN** the browser context menu shows "Open in new tab" with the correct `/portal-shell/hold-overview` href

### Requirement: Reject history detail table displays WORKFLOWNAME in DuckDB mode
The reject-history detail table SHALL display the WORKFLOW column with correct data when the frontend DuckDB-WASM engine is active (datasets ≥ 5,000 rows).

#### Scenario: WORKFLOWNAME visible in DuckDB mode
- **WHEN** a reject-history query returns ≥ 5,000 rows and DuckDB-WASM mode activates
- **THEN** the detail table WORKFLOW column displays `WORKFLOWNAME` values from the parquet spool data, matching the server-side `/view` API output

#### Scenario: WORKFLOWNAME graceful null handling
- **WHEN** a parquet spool file does not contain a WORKFLOWNAME column (legacy cache)
- **THEN** the detail table WORKFLOW column displays empty string (not an error)

### Requirement: Docker spool registration resilience
The Docker deployment SHALL successfully register spool files without "failed to register" errors under normal operating conditions.

#### Scenario: Spool directory exists at container startup
- **WHEN** the Docker container starts
- **THEN** the `QUERY_SPOOL_DIR` path and all required subdirectories exist and are writable

#### Scenario: Spool registration succeeds in container
- **WHEN** a query produces a parquet spool file inside the Docker container
- **THEN** `register_spool_file` successfully moves the file to the canonical path and stores metadata in Redis
