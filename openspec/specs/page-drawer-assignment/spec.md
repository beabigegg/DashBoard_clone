## Purpose
Define stable requirements for page-drawer-assignment.

## Requirements


### Requirement: Admin SHALL be able to assign a page to a drawer
The system SHALL allow admin users to assign a page to a specific drawer by setting its `drawer_id` via the existing page update API.

#### Scenario: Assign page to a drawer
- **WHEN** admin sends PUT `/admin/api/pages/<route>` with `{"drawer_id": "queries"}`
- **THEN** the page SHALL be associated with the specified drawer

#### Scenario: Assign page to non-existent drawer
- **WHEN** admin sends PUT `/admin/api/pages/<route>` with a `drawer_id` that does not exist
- **THEN** the system SHALL return 400 Bad Request with an error message

### Requirement: Admin SHALL be able to set page order within a drawer
The system SHALL allow admin users to control the display order of pages within a drawer.

#### Scenario: Set page order
- **WHEN** admin sends PUT `/admin/api/pages/<route>` with `{"order": 3}`
- **THEN** the page SHALL be displayed at position 3 within its drawer on next portal load

### Requirement: Pages without a drawer assignment SHALL NOT appear in the sidebar
Pages that have no `drawer_id` (e.g., sub-pages like `/wip-detail`, `/hold-detail`) SHALL NOT be rendered in the portal sidebar, but SHALL remain accessible via their direct routes.

#### Scenario: Sub-page without drawer assignment
- **WHEN** a page exists in `page_status.json` without a `drawer_id`
- **THEN** the page SHALL NOT appear in any sidebar drawer
- **THEN** the page SHALL still be accessible via its direct URL

### Requirement: Page drawer assignment SHALL be configurable from the admin UI
The existing `/admin/pages` page table SHALL include a drawer assignment dropdown and order controls for each page.

#### Scenario: Admin changes page drawer via UI
- **WHEN** admin selects a different drawer from the dropdown for a page
- **THEN** the UI SHALL call the page update API with the new `drawer_id`

#### Scenario: Admin clears drawer assignment via UI
- **WHEN** admin selects "未分類" (unassigned) from the dropdown
- **THEN** the page's `drawer_id` SHALL be removed and the page SHALL no longer appear in the sidebar
