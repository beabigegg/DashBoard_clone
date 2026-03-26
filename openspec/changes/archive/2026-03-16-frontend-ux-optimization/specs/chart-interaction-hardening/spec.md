## ADDED Requirements

### Requirement: VChart autoresize SHALL use throttled mode
All `<VChart>` component instances across the project SHALL use throttled autoresize to prevent excessive resize event processing.

#### Scenario: Throttle configuration
- **WHEN** any VChart component renders
- **THEN** the `autoresize` prop SHALL be set to `{ throttle: 100 }` (100ms throttle)

#### Scenario: Consistent across all chart components
- **WHEN** searching for `<VChart` across all `.vue` files
- **THEN** every instance SHALL include `:autoresize="{ throttle: 100 }"` or equivalent

### Requirement: Chart containers SHALL have ARIA semantics
All chart visualization containers SHALL include ARIA attributes to provide accessible descriptions for screen readers.

#### Scenario: Chart ARIA label
- **WHEN** a chart component renders its VChart container
- **THEN** the container wrapper SHALL have `role="img"` and a descriptive `aria-label` in Chinese (e.g., "每日不良趨勢圖")

#### Scenario: ARIA label reflects chart purpose
- **WHEN** a TrendChart renders in reject-history
- **THEN** `aria-label` SHALL describe the chart's content (e.g., "退貨數量趨勢圖")
- **THEN** the label SHALL NOT be a generic string like "圖表"

### Requirement: Pareto Grid SHALL provide clear interaction affordances
The Pareto Grid component SHALL visually communicate that cells are clickable and provide adequate hover feedback.

#### Scenario: Cursor affordance
- **WHEN** a user hovers over a Pareto Grid cell
- **THEN** the cursor SHALL change to `pointer`

#### Scenario: Hover highlight
- **WHEN** a user hovers over a Pareto Grid cell
- **THEN** the cell background SHALL change to `theme('colors.surface.hover')` (not just opacity change)

#### Scenario: CSS contract compliance
- **WHEN** Pareto Grid hover styles are defined
- **THEN** the styles SHALL be scoped under `.theme-reject-history` per CSS contract 4.3
- **THEN** color values SHALL use `theme()` references per CSS contract 2.3
