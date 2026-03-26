## ADDED Requirements

### Requirement: Interactive elements SHALL have visible focus indicators
All interactive elements (buttons, links, form controls, clickable table cells) SHALL display a visible `:focus-visible` outline when focused via keyboard navigation.

#### Scenario: Focus ring on ui-btn
- **WHEN** a user tabs to any element with class `ui-btn`, `ui-btn--primary`, or `ui-btn--ghost`
- **THEN** a 2px solid outline using `theme('colors.brand.500')` with 2px offset SHALL be visible

#### Scenario: Focus ring on drawer navigation links
- **WHEN** a user tabs to a `.drawer-link` in the portal sidebar
- **THEN** a visible focus outline SHALL appear matching the global focus ring style

#### Scenario: Focus ring on MultiSelect trigger
- **WHEN** a user tabs to a `.multi-select-trigger` button
- **THEN** a visible focus outline SHALL appear matching the global focus ring style

#### Scenario: Focus ring on pagination buttons
- **WHEN** a user tabs to pagination control buttons
- **THEN** a visible focus outline SHALL appear matching the global focus ring style

### Requirement: Portal shell SHALL provide semantic landmarks
The portal shell layout SHALL include proper HTML5 landmark elements to enable screen reader navigation.

#### Scenario: Main content landmark
- **WHEN** the portal shell renders
- **THEN** the page content area SHALL be wrapped in a `<main id="main-content">` element

#### Scenario: Navigation landmark
- **WHEN** the portal shell renders the sidebar
- **THEN** the sidebar `<aside>` SHALL have `role="navigation"` and `aria-label="主選單"`

#### Scenario: Skip-to-content link
- **WHEN** the portal shell renders
- **THEN** a visually-hidden skip link SHALL exist as the first focusable element
- **THEN** activating the skip link SHALL move focus to `#main-content`

### Requirement: Animations SHALL respect prefers-reduced-motion
All CSS animations and transitions across feature modules SHALL be disabled when the user's OS has `prefers-reduced-motion: reduce` enabled.

#### Scenario: WIP domain reduced motion
- **WHEN** `prefers-reduced-motion: reduce` is active
- **THEN** `.refresh-indicator` spin animation, `.refresh-success` fadeOut, and `.summary-value` valueUpdate animations within `:is(.theme-wip-overview, .theme-wip-detail)` SHALL be disabled

#### Scenario: Resource domain reduced motion
- **WHEN** `prefers-reduced-motion: reduce` is active
- **THEN** hover-lift transforms and status dot animations within `:is(.theme-resource, .theme-resource-history)` SHALL be disabled

#### Scenario: Theme-scoped compliance
- **WHEN** reduced-motion rules are added to feature CSS files
- **THEN** all rules SHALL be scoped under the corresponding theme root class per CSS contract 4.3

### Requirement: Text colors SHALL meet WCAG AA contrast ratio
All text color tokens used on white/light backgrounds SHALL achieve a minimum contrast ratio of 4.5:1.

#### Scenario: text.muted contrast compliance
- **WHEN** `text.muted` is rendered on a `surface.card` (#ffffff) background
- **THEN** the contrast ratio SHALL be at least 4.5:1
- **THEN** the `text.muted` value in `tailwind.config.js` SHALL be `#64748b` or darker
