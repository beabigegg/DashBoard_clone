## MODIFIED Requirements

### Requirement: Portal SHALL provide a SPA shell driven by Vue Router
The portal frontend SHALL use a single SPA shell entry and Vue Router to render page modules without iframe embedding, and SHALL route each page through native route-view integration. The shell layout SHALL use a full-viewport fluid layout with flexbox, removing all max-width constraints and block-centered styling. The main content area (`.shell-content`) SHALL fill available space as a flex child, and the sidebar SHALL be a collapsible flex child that pushes content when expanded on desktop. The content area class SHALL be `.shell-content` (not `.content`) to avoid CSS collision with page-level `.content` classes.

#### Scenario: Drawer navigation renders integrated route view
- **WHEN** a user clicks a sidebar page entry whose migration mode is `native`
- **THEN** the active route SHALL be updated through Vue Router
- **THEN** the main content area SHALL render the corresponding page module inside shell route-view without iframe usage
- **THEN** the content area SHALL fill the available viewport width minus the sidebar width (if sidebar is expanded)

#### Scenario: Shell layout fills full viewport
- **WHEN** the portal shell renders
- **THEN** the shell SHALL span the full viewport width with no max-width constraint
- **THEN** the header SHALL span edge-to-edge with no border-radius
- **THEN** the sidebar and content area SHALL have no outer borders or border-radius

#### Scenario: Page-level max-width constraints are removed when embedded
- **WHEN** a page module registered in the shell route contracts renders inside `.shell-content`
- **THEN** page-level max-width constraints SHALL be overridden to allow full-width rendering
- **THEN** page-level duplicate padding SHALL be removed to avoid double spacing
- **THEN** standalone page rendering (outside the shell) SHALL remain unaffected

#### Scenario: Shell content class avoids collision with page-level classes
- **WHEN** a page module that uses its own `.content` class renders inside the shell
- **THEN** the shell's content wrapper (`.shell-content`) SHALL NOT interfere with the page's `.content` styling
