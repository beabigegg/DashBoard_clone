## ADDED Requirements

### Requirement: Every frontend SPA module SHALL have at least one test file
Each frontend SPA application under `frontend/src/` that contains composables, utilities, or significant business logic SHALL have a corresponding test file in `frontend/tests/`.

#### Scenario: SPA module with no existing test gets coverage
- **WHEN** a frontend SPA module exists with composables or business logic and no corresponding test file
- **THEN** a test file SHALL be created covering the primary composable or utility functions

#### Scenario: Identified gap modules
- **WHEN** auditing the following frontend modules: `resource-status`, `resource-history`, `production-history`, `admin-dashboard`, `admin-performance`, `admin-user-usage-kpi`, `anomaly-overview`, `mid-section-defect` (composable-level), `material-trace` (composable-level)
- **THEN** each SHALL have at least one test file exercising its key logic

### Requirement: Frontend tests SHALL use Node.js built-in test runner
All new frontend tests SHALL use `node:test` and `node:assert` modules, consistent with the existing 23 test files.

#### Scenario: New frontend test file
- **WHEN** a new test file is created in `frontend/tests/`
- **THEN** it SHALL import from `node:test` (describe, it) and `node:assert` (strict)

### Requirement: Frontend tests SHALL cover data transformation logic
For modules that transform API responses into display data, tests SHALL verify the transformation produces correct output for representative inputs.

#### Scenario: Composable transforms API data
- **WHEN** a composable function receives an API response object
- **THEN** the test SHALL verify the transformed output matches expected display values

#### Scenario: Edge case handling
- **WHEN** a composable receives empty, null, or malformed input
- **THEN** the test SHALL verify graceful handling without throwing
