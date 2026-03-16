## Purpose
Define stable requirements for spa-shell-navigation.
## Requirements
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

#### Scenario: Admin route appears as governed target
- **WHEN** an admin user opens shell navigation
- **THEN** `/admin/pages` and `/admin/performance` SHALL be exposed as governed navigation targets per access policy

#### Scenario: Deferred route is excluded from this phase route-governance requirement
- **WHEN** phase-level shell-governance compliance is evaluated
- **THEN** `/tables`, `/excel-query`, `/query-tool`, and `/mid-section-defect` SHALL be treated as deferred and excluded from pass/fail criteria for this phase

### Requirement: Existing route contracts SHALL remain stable in SPA mode
Migration to the shell-first SPA model SHALL preserve route/query compatibility for in-scope routes while introducing canonical shell routing policy and explicit compatibility handling.

#### Scenario: Canonical shell path behavior for in-scope routes
- **WHEN** a user opens an in-scope report route via canonical shell path
- **THEN** route behavior and query semantics SHALL remain compatible with established baseline behavior

#### Scenario: Compatibility policy for direct route entry
- **WHEN** a user opens an in-scope report route via direct non-canonical entry
- **THEN** the system SHALL apply explicit compatibility policy (preserve behavior or compatibility redirect) without breaking route semantics

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

### Requirement: Canonical redirect scope boundaries SHALL be explicit and intentional
Canonical shell direct-entry redirects SHALL apply only to governed in-scope report routes and SHALL explicitly exclude admin external targets with documented rationale.

#### Scenario: In-scope report route direct entry
- **WHEN** SPA shell mode is enabled and a user enters an in-scope report route directly
- **THEN** the system SHALL redirect to the canonical `/portal-shell/...` route while preserving query semantics

#### Scenario: Admin external target direct entry
- **WHEN** SPA shell mode is enabled and a user enters `/admin/pages` or `/admin/performance` directly
- **THEN** the system SHALL NOT apply report-route canonical redirect policy
- **THEN** the exclusion rationale SHALL be documented in code-level comments or governance docs

### Requirement: Missing-required-parameter redirects SHALL avoid avoidable multi-hop chains
Routes with server-side required query parameters SHALL minimize redirect hops under SPA shell mode.

#### Scenario: Hold detail missing reason in SPA shell mode
- **WHEN** a user opens `/hold-detail` without `reason` while SPA shell mode is enabled
- **THEN** the route SHALL resolve via a single-hop redirect to the canonical overview shell path

