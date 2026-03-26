## MODIFIED Requirements

### Requirement: Pure Vite pages SHALL be served as static HTML
The system SHALL support serving Vite-built HTML pages directly via Flask without Jinja2 rendering.

#### Scenario: Serve pure Vite page
- **WHEN** user navigates to a pure Vite page route (e.g., `/qc-gate`)
- **THEN** Flask SHALL serve the pre-built HTML file from `static/dist/` via `send_from_directory`
- **THEN** the HTML SHALL NOT pass through Jinja2 template rendering

#### Scenario: Page works as top-level navigation target
- **WHEN** a pure Vite page is opened from portal direct navigation
- **THEN** the page SHALL render correctly as a top-level route without iframe embedding dependency
- **THEN** page functionality SHALL NOT rely on portal-managed frame lifecycle

#### Scenario: Direct URL with query parameters remains valid
- **WHEN** users directly open a pure Vite route with existing query parameters (e.g., `/wip-detail?workcenter=...`)
- **THEN** the page SHALL preserve existing parameter semantics and load behavior
- **THEN** SPA shell integration SHALL NOT break direct route entry
