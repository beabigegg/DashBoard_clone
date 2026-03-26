## MODIFIED Requirements

### Requirement: Portal SHALL provide a SPA shell driven by Vue Router
The portal frontend SHALL use a single SPA shell entry and Vue Router to render page modules without iframe embedding, and SHALL route each page through either native route-view integration or a temporary wrapper component.

#### Scenario: Drawer navigation renders integrated route view
- **WHEN** a user clicks a sidebar page entry whose migration mode is `native`
- **THEN** the active route SHALL be updated through Vue Router
- **THEN** the main content area SHALL render the corresponding page module inside shell route-view without iframe usage

#### Scenario: Wrapper route remains available during migration
- **WHEN** a user clicks a sidebar page entry whose migration mode is `wrapper`
- **THEN** Vue Router SHALL render the wrapper host in shell content area
- **THEN** the wrapper SHALL preserve page reachability until native rewrite is completed

### Requirement: Existing route contracts SHALL remain stable in SPA mode
Migration to SPA shell SHALL preserve existing route paths, deep-link behavior, and query semantics during both native and wrapper phases.

#### Scenario: Direct route entry remains functional
- **WHEN** a user opens an existing route directly (bookmark or refresh)
- **THEN** the route SHALL resolve to the same page functionality as before migration
- **THEN** required query parameters SHALL continue to be interpreted with compatible semantics

#### Scenario: Query continuity across shell navigation
- **WHEN** users navigate from shell list pages to detail pages and back
- **THEN** query-state parameters required by list/detail workflows SHALL remain consistent with pre-migration behavior

### Requirement: SPA shell navigation SHALL enforce page visibility rules
SPA navigation SHALL respect backend-defined drawer and page visibility outcomes, including admin entry visibility and route fallback for hidden routes.

#### Scenario: Non-admin visibility in SPA shell
- **WHEN** a non-admin user opens the shell
- **THEN** routes and drawer items restricted to admin-only visibility SHALL NOT be presented as navigable entries

#### Scenario: Admin visibility in SPA shell
- **WHEN** an admin user opens the shell
- **THEN** pages allowed by drawer and page status rules SHALL be presented as navigable entries
- **THEN** admin entry links exposed by the shell SHALL remain reachable

#### Scenario: Hidden or unknown route fallback
- **WHEN** a user navigates to a route that is not visible or not registered in the current shell navigation set
- **THEN** the shell SHALL redirect to a safe fallback route
- **THEN** the shell SHALL NOT expose iframe-based fallback rendering
