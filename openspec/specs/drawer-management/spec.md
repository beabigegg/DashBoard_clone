## Purpose
Define stable requirements for drawer-management.

## Requirements


### Requirement: Admin SHALL be able to create drawers
The system SHALL allow admin users to create new navigation drawers via API, specifying a name, an order value, and an optional `admin_only` flag.

#### Scenario: Create a new drawer
- **WHEN** admin sends POST `/admin/api/drawers` with `{"name": "自訂分類", "order": 4}`
- **THEN** the system SHALL create a new drawer with a generated kebab-case id and persist it to `page_status.json`

#### Scenario: Create drawer with duplicate name
- **WHEN** admin sends POST `/admin/api/drawers` with a name that already exists
- **THEN** the system SHALL return 409 Conflict with an error message

### Requirement: Admin SHALL be able to rename drawers
The system SHALL allow admin users to update a drawer's name via API.

#### Scenario: Rename a drawer
- **WHEN** admin sends PUT `/admin/api/drawers/<id>` with `{"name": "新名稱"}`
- **THEN** the system SHALL update the drawer name and persist the change

### Requirement: Admin SHALL be able to reorder drawers
The system SHALL allow admin users to change a drawer's sort order via API.

#### Scenario: Change drawer order
- **WHEN** admin sends PUT `/admin/api/drawers/<id>` with `{"order": 2}`
- **THEN** the system SHALL update the drawer order and the sidebar SHALL reflect the new order on next page load

### Requirement: Admin SHALL be able to delete empty drawers
The system SHALL allow admin users to delete a drawer only when no pages are assigned to it.

#### Scenario: Delete an empty drawer
- **WHEN** admin sends DELETE `/admin/api/drawers/<id>` and the drawer has no assigned pages
- **THEN** the system SHALL remove the drawer from the configuration

#### Scenario: Attempt to delete a drawer with assigned pages
- **WHEN** admin sends DELETE `/admin/api/drawers/<id>` and the drawer still has assigned pages
- **THEN** the system SHALL return 409 Conflict with an error listing the assigned pages

### Requirement: Admin SHALL be able to list all drawers
The system SHALL provide an API to retrieve all drawers with their metadata.

#### Scenario: List all drawers
- **WHEN** admin sends GET `/admin/api/drawers`
- **THEN** the system SHALL return all drawers sorted by their `order` field

### Requirement: Drawer management SHALL be accessible from the admin UI
The existing `/admin/pages` page SHALL include a drawer management section where admin can create, rename, reorder, and delete drawers.

#### Scenario: Admin opens page management
- **WHEN** admin navigates to the page management UI
- **THEN** the UI SHALL display a drawer list with controls for add, rename, reorder, and delete
