## MODIFIED Requirements

### Requirement: Portal SHALL provide a SPA shell driven by Vue Router
The portal frontend SHALL use a single SPA shell entry and Vue Router to render in-scope page modules without iframe embedding. In-scope routes for this phase SHALL include the governed report routes and admin surfaces `/admin/pages` and `/admin/performance`, while deferred routes (`/tables`, `/excel-query`, `/query-tool`, `/mid-section-defect`) are explicitly excluded from this phase contract.

#### Scenario: In-scope route renders through shell governance
- **WHEN** a user navigates to an in-scope shell-governed route
- **THEN** the route SHALL resolve through Vue Router with shell contract metadata
- **THEN** the shell SHALL render the corresponding module/target without iframe fallback

#### Scenario: Shell provides main content landmark
- **WHEN** the portal shell renders
- **THEN** the page content area SHALL be wrapped in a `<main id="main-content">` element
- **THEN** the sidebar SHALL have `role="navigation"` and `aria-label="主選單"`

#### Scenario: Shell provides skip-to-content link
- **WHEN** the portal shell renders
- **THEN** a visually-hidden skip link SHALL exist as the first focusable element in the DOM
- **THEN** activating the skip link SHALL move keyboard focus to `#main-content`
