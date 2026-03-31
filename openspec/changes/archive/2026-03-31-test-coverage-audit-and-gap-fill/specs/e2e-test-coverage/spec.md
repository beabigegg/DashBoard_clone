## ADDED Requirements

### Requirement: Every user-facing page SHALL have at least one e2e test
Each frontend SPA application that represents a user-facing page SHALL have a corresponding `tests/e2e/test_<page>_e2e.py` file exercising the primary user workflow.

#### Scenario: Page with no existing e2e test gets coverage
- **WHEN** a page exists as a frontend SPA application with no corresponding e2e test
- **THEN** an e2e test file SHALL be created that navigates to the page, verifies it loads, and exercises the primary query/filter workflow

#### Scenario: Identified gap pages
- **WHEN** auditing the following pages: `production-history`, `anomaly-overview`, `admin-dashboard`, `admin-performance`, `admin-user-usage-kpi`
- **THEN** each SHALL have a dedicated e2e test file

### Requirement: E2E tests SHALL use existing playwright fixtures
All new e2e tests SHALL use the `app_server`, `browser_context_args`, and `api_base_url` fixtures from `tests/e2e/conftest.py`.

#### Scenario: New e2e test setup
- **WHEN** a new e2e test file is created
- **THEN** it SHALL import and use the shared e2e conftest fixtures for server URL and browser configuration

### Requirement: E2E tests SHALL verify page load and primary content
Each e2e test SHALL at minimum verify that the page loads without JavaScript errors and that the primary content area renders.

#### Scenario: Page loads successfully
- **WHEN** the e2e test navigates to the page URL
- **THEN** the page SHALL render without console errors and the main content container SHALL be visible

#### Scenario: Primary query workflow
- **WHEN** the page has a query/filter form
- **THEN** the e2e test SHALL fill the form, submit, and verify that results appear in the data area
