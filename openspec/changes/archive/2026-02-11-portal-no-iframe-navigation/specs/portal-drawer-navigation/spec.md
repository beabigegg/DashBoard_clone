## MODIFIED Requirements

### Requirement: Portal Navigation SHALL Group Entries by Functional Drawers
The portal SHALL group navigation entries into functional drawers as defined in the `drawers` configuration of `page_status.json`, rendered by the active portal runtime (server template or SPA shell) without changing drawer assignment semantics.

#### Scenario: Drawer grouping visibility
- **WHEN** users open the portal
- **THEN** the sidebar SHALL display drawers in the order defined by each drawer's `order` field
- **THEN** each drawer SHALL show only the pages assigned to it via `drawer_id`, sorted by each page's `order` field

#### Scenario: Admin-only drawer visibility
- **WHEN** a drawer has `admin_only: true` and the current user is not admin
- **THEN** the drawer and all its pages SHALL NOT be rendered in the sidebar

#### Scenario: Empty drawer visibility
- **WHEN** a drawer has no visible pages (all filtered out by page visibility checks)
- **THEN** the drawer group title SHALL NOT be rendered

### Requirement: Existing Page Behavior SHALL Remain Compatible
The portal navigation refactor SHALL preserve existing target routes while replacing iframe-based page embedding with route-driven navigation.

#### Scenario: Route continuity
- **WHEN** a user selects an existing page entry from a drawer
- **THEN** the corresponding original route SHALL be loaded without changing page business logic behavior

#### Scenario: Direct navigation without iframe
- **WHEN** a sidebar item is clicked
- **THEN** the browser SHALL navigate to the page's route in the same window
- **THEN** the portal SHALL NOT render or activate iframe elements for page content

## ADDED Requirements

### Requirement: Drawer Configuration and Visibility SHALL Remain Deterministic During Migration
Migration to SPA navigation SHALL preserve the effective drawer visibility outcomes defined by current `drawers + pages + status + admin_only` rules.

#### Scenario: Non-admin visible drawer pages remain stable
- **WHEN** a non-admin user opens the portal after migration
- **THEN** only pages with released visibility in non-admin drawers SHALL be visible
- **THEN** admin-only drawers SHALL remain hidden

#### Scenario: Admin visible drawer pages remain stable
- **WHEN** an admin user opens the portal after migration
- **THEN** all pages allowed by drawer assignment and page status rules SHALL remain visible

#### Scenario: Duplicate order values resolve deterministically
- **WHEN** multiple pages or drawers share the same `order` value
- **THEN** rendering order SHALL still be deterministic and repeatable across requests
