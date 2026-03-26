## ADDED Requirements

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
