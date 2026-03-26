## ADDED Requirements

### Requirement: Hold overview filter panel SHALL be responsive
The hold-overview filter panel grid layout SHALL adapt to narrow viewports by stacking filters vertically.

#### Scenario: Mobile layout breakpoint
- **WHEN** the viewport width is 700px or below
- **THEN** the filter panel grid SHALL switch to `grid-template-columns: 1fr` (single column)

#### Scenario: Theme-scoped rule
- **WHEN** the responsive breakpoint is defined in `hold-overview/style.css`
- **THEN** it SHALL be scoped under `.theme-hold-overview` per CSS contract 4.3

### Requirement: MultiSelect SHALL show loading state in trigger
The MultiSelect trigger button SHALL visually indicate when options are being loaded.

#### Scenario: Loading spinner in trigger
- **WHEN** the `loading` prop is `true` and the dropdown is closed
- **THEN** a small spinner icon SHALL be displayed inside the trigger button

#### Scenario: Trigger disabled during loading
- **WHEN** the `loading` prop is `true`
- **THEN** the trigger button SHALL be disabled and not openable

### Requirement: MultiSelect SHALL use animated SVG chevron
The MultiSelect dropdown indicator SHALL use an SVG chevron icon with rotation animation instead of unicode characters.

#### Scenario: Chevron rotation on open
- **WHEN** the MultiSelect dropdown opens
- **THEN** the chevron icon SHALL rotate 180 degrees with a smooth transition

#### Scenario: Chevron rotation on close
- **WHEN** the MultiSelect dropdown closes
- **THEN** the chevron icon SHALL rotate back to 0 degrees

#### Scenario: No unicode arrow characters
- **WHEN** the MultiSelect component renders
- **THEN** no `▲` or `▼` unicode characters SHALL be used for the dropdown indicator

### Requirement: ErrorBanner component for dismissible error messages
The system SHALL provide an `ErrorBanner` component at `shared-ui/components/ErrorBanner.vue` with dismiss and action slot support.

#### Scenario: Error message display
- **WHEN** an `ErrorBanner` receives a `message` prop
- **THEN** it SHALL display the message with error styling (red background, icon)

#### Scenario: Dismiss button
- **WHEN** the `dismissible` prop is `true` (default)
- **THEN** an X close button SHALL be rendered
- **THEN** clicking the X button SHALL emit a `dismiss` event

#### Scenario: Action slot for retry
- **WHEN** a consumer provides content in the `action` slot
- **THEN** the slot content SHALL be rendered within the banner (e.g., a retry button)

#### Scenario: CSS inventory update
- **WHEN** `ErrorBanner.vue` is created with `<style scoped>`
- **THEN** `contract/css_inventory.md` SHALL be updated to include the new component

### Requirement: FilterToolbar SHALL support chip mode for active filters

#### Scenario: Chip display of active filters
- **WHEN** `FilterToolbar` receives an `activeFilters` array prop with `[{ key, label, value }]` items
- **THEN** it SHALL render a row of `Chip` components below the filter controls
- **THEN** each chip SHALL be `removable` and emit `@remove-filter` with the filter key

#### Scenario: No active filters
- **WHEN** `activeFilters` is empty or not provided
- **THEN** no chip row SHALL be rendered

### Requirement: FilterToolbar SHALL support collapsible mode

#### Scenario: Collapsed state
- **WHEN** `FilterToolbar` has `:collapsible="true"` and is in collapsed state
- **THEN** only the active filter chips and an expand toggle button SHALL be visible
- **THEN** the filter controls SHALL be hidden with `max-height: 0` and `overflow: hidden`

#### Scenario: Expand toggle
- **WHEN** the user clicks the expand toggle button
- **THEN** the filter controls SHALL expand with `max-height` transition over `var(--motion-normal)`
- **THEN** the toggle icon SHALL rotate from `ChevronDown` to `ChevronUp`
