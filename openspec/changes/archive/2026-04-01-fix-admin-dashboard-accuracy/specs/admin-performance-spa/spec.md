## ADDED Requirements

### Requirement: Admin Performance header SHALL use shared PageHeader component
The Admin Performance `App.vue` SHALL replace its custom `.perf-header` with the shared `PageHeader` component from `shared-ui/components/PageHeader.vue`.

#### Scenario: Header renders with PageHeader component
- **WHEN** the Admin Performance page loads
- **THEN** the header SHALL use the `header-gradient` class with 4-corner `border-radius: 12px`
- **THEN** the title SHALL display "效能監控儀表板" at `font-size: 24px`

#### Scenario: Auto-refresh and manual refresh remain functional
- **WHEN** the Admin Performance header renders with PageHeader
- **THEN** the auto-refresh toggle (checkbox + label) SHALL remain accessible
- **THEN** the manual refresh button SHALL trigger `refreshAll()`

### Requirement: Admin Performance container SHALL use 1800px max-width
The `.perf-dashboard` container SHALL use `max-width: 1800px` to align with business page layout.

#### Scenario: Wide screen layout
- **WHEN** the viewport is wider than 1800px
- **THEN** the admin performance content SHALL be centered with `max-width: 1800px`
