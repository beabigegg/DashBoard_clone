## Purpose
Define stable requirements for collapsible-sidebar-drawer.

## Requirements

### Requirement: Sidebar SHALL be collapsible via a toggle button
The portal shell SHALL provide a toggle button in the header that collapses and expands the sidebar. On desktop viewports (>900px), collapsing SHALL animate the sidebar width from 240px to 0px using push mode, causing the content area to resize and fill the freed space. Expanding SHALL reverse the animation.

#### Scenario: Desktop sidebar collapse
- **WHEN** a user clicks the sidebar toggle button on a desktop viewport
- **AND** the sidebar is currently expanded
- **THEN** the sidebar width SHALL animate to 0px over 300ms
- **THEN** the content area SHALL expand to fill the full viewport width

#### Scenario: Desktop sidebar expand
- **WHEN** a user clicks the sidebar toggle button on a desktop viewport
- **AND** the sidebar is currently collapsed
- **THEN** the sidebar width SHALL animate to 240px over 300ms
- **THEN** the content area SHALL shrink to accommodate the sidebar

### Requirement: Mobile sidebar SHALL use overlay drawer mode
On mobile viewports (<=900px), the sidebar SHALL behave as a fixed-position overlay drawer that slides in from the left, with a semi-transparent backdrop covering the content area.

#### Scenario: Mobile sidebar open
- **WHEN** a user taps the toggle button on a mobile viewport
- **AND** the sidebar is currently hidden
- **THEN** the sidebar SHALL slide in from the left as a fixed overlay (280px width)
- **THEN** a semi-transparent backdrop SHALL appear behind the sidebar and above the content

#### Scenario: Mobile sidebar close via backdrop
- **WHEN** a user taps the backdrop overlay
- **THEN** the sidebar SHALL slide out to the left
- **THEN** the backdrop SHALL fade out

#### Scenario: Mobile sidebar close via Escape key
- **WHEN** the mobile sidebar overlay is open
- **AND** a user presses the Escape key
- **THEN** the sidebar SHALL close

#### Scenario: Mobile sidebar closes on navigation
- **WHEN** the mobile sidebar overlay is open
- **AND** a user clicks a navigation link
- **THEN** the sidebar SHALL automatically close after the route change

### Requirement: Sidebar state SHALL persist within the browser session
The collapsed/expanded state of the desktop sidebar SHALL be persisted to `sessionStorage` so that the preference survives page refreshes within the same browser tab.

#### Scenario: State persistence on refresh
- **WHEN** a user collapses the sidebar and refreshes the page
- **THEN** the sidebar SHALL remain collapsed after reload

#### Scenario: New tab starts expanded
- **WHEN** a user opens the portal in a new browser tab
- **THEN** the sidebar SHALL default to expanded regardless of other tabs' state

### Requirement: Sidebar transitions SHALL respect reduced-motion preference
All sidebar transitions (width animation, overlay slide, backdrop fade) SHALL be disabled when the user has `prefers-reduced-motion: reduce` enabled.

#### Scenario: Reduced motion disables sidebar animation
- **WHEN** the user's OS or browser has reduced-motion enabled
- **AND** the user toggles the sidebar
- **THEN** the sidebar state SHALL change instantly without animation

### Requirement: Toggle button SHALL be accessible
The sidebar toggle button SHALL include `aria-label` and `aria-expanded` attributes for screen reader accessibility.

#### Scenario: Screen reader announces toggle state
- **WHEN** a screen reader user focuses the toggle button
- **THEN** the button SHALL announce its current expanded/collapsed state via `aria-expanded`
- **THEN** the button SHALL have an `aria-label` describing its purpose
