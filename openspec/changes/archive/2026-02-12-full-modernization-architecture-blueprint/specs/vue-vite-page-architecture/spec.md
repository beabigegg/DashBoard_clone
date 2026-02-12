## MODIFIED Requirements

### Requirement: Pure Vite pages SHALL be served as static HTML
The system SHALL serve in-scope pure Vite pages through backend static HTML delivery under a shell-first canonical routing policy. Direct-entry compatibility for in-scope routes SHALL be explicit and governed. Admin targets `/admin/pages` and `/admin/performance` SHALL be represented as governed shell navigation targets, while maintaining backend auth/session authority.

#### Scenario: In-scope canonical shell entry
- **WHEN** a user navigates to an in-scope canonical shell route
- **THEN** the shell SHALL render the target route via governed route contracts and static asset delivery

#### Scenario: Direct-entry compatibility policy for in-scope routes
- **WHEN** a user opens an in-scope route through direct non-canonical entry
- **THEN** the system SHALL apply explicit compatibility behavior without breaking established query semantics

#### Scenario: Admin targets in shell governance
- **WHEN** shell navigation is rendered for an authorized admin user
- **THEN** `/admin/pages` and `/admin/performance` SHALL be reachable through governed admin navigation targets

#### Scenario: Deferred routes excluded from this phase architecture criteria
- **WHEN** this phase architecture compliance is evaluated
- **THEN** `/tables`, `/excel-query`, `/query-tool`, and `/mid-section-defect` SHALL be excluded and handled in a follow-up change
