## ADDED Requirements

### Requirement: Portal SHALL provide a SPA shell driven by Vue Router
The portal frontend SHALL use a single SPA shell entry and Vue Router to render page modules without iframe embedding.

#### Scenario: Drawer navigation renders router view
- **WHEN** a user clicks a sidebar page entry
- **THEN** the active route SHALL be updated through Vue Router
- **THEN** the main content area SHALL render the corresponding route view without iframe usage

### Requirement: Existing route contracts SHALL remain stable in SPA mode
Migration to SPA shell SHALL preserve existing route paths and deep-link behavior.

#### Scenario: Direct route entry remains functional
- **WHEN** a user opens an existing route directly (bookmark or refresh)
- **THEN** the route SHALL resolve to the same page functionality as before migration
- **THEN** required query parameters SHALL continue to be interpreted with compatible semantics

### Requirement: SPA shell navigation SHALL enforce page visibility rules
SPA navigation SHALL respect backend-defined drawer and page visibility outcomes.

#### Scenario: Non-admin visibility in SPA shell
- **WHEN** a non-admin user opens the shell
- **THEN** routes and drawer items restricted to admin-only visibility SHALL NOT be presented as navigable entries

#### Scenario: Admin visibility in SPA shell
- **WHEN** an admin user opens the shell
- **THEN** pages allowed by drawer and page status rules SHALL be presented as navigable entries
