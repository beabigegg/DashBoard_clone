## MODIFIED Requirements

### Requirement: Portal SHALL provide a SPA shell driven by Vue Router
The portal frontend SHALL use a single SPA shell entry and Vue Router to render in-scope page modules without iframe embedding. In-scope routes for this phase SHALL include the governed report routes and admin surfaces `/admin/pages` and `/admin/performance`, while deferred routes (`/tables`, `/excel-query`, `/query-tool`, `/mid-section-defect`) are explicitly excluded from this phase contract.

#### Scenario: In-scope route renders through shell governance
- **WHEN** a user navigates to an in-scope shell-governed route
- **THEN** the route SHALL resolve through Vue Router with shell contract metadata
- **THEN** the shell SHALL render the corresponding module/target without iframe fallback

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
