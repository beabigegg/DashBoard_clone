## Purpose
Define stable requirements for the SummaryCard and SummaryCardGroup shared-ui components.

## Requirements

### Requirement: SummaryCard component SHALL provide unified KPI display

The system SHALL provide a `SummaryCard` component at `shared-ui/components/SummaryCard.vue` for displaying key performance indicators with consistent styling.

#### Scenario: Basic KPI rendering
- **WHEN** `SummaryCard` receives `label` and `value` props
- **THEN** it SHALL render a card with label (12px, uppercase, muted) above value (28px, bold)
- **THEN** the card SHALL have a 3px colored top accent bar matching the `accent` prop color

#### Scenario: Number formatting
- **WHEN** `format="number"` is set
- **THEN** the value SHALL be formatted using `toLocaleString('zh-TW')`
- **WHEN** `format="percent"` is set
- **THEN** the value SHALL be displayed with `%` suffix and one decimal place
- **WHEN** `format="duration"` is set
- **THEN** the value SHALL be displayed with one decimal and appropriate unit suffix

#### Scenario: Accent color mapping
- **WHEN** `accent` prop is one of: `brand`, `success`, `warning`, `danger`, `info`, `neutral`, `prd`, `sby`, `udt`, `sdt`, `egt`, `nst`
- **THEN** the top accent bar and value text color SHALL map to the corresponding design token color

#### Scenario: Sub-content slot
- **WHEN** a `#sub` slot is provided
- **THEN** it SHALL render below the value in 12px muted style
- **WHEN** no `#sub` slot is provided
- **THEN** no sub-content area SHALL be rendered

### Requirement: SummaryCard SHALL support interactive (clickable) mode

#### Scenario: Clickable card with hover effect
- **WHEN** the `clickable` prop is true
- **THEN** the card SHALL have `cursor: pointer` and hover effect (`translateY(-3px)` + elevated shadow)
- **THEN** clicking SHALL emit a `@click` event

#### Scenario: Active state
- **WHEN** `clickable` and `active` props are both true
- **THEN** the card SHALL display a blue border glow (`brand.500` box-shadow) and subtle scale transform
- **THEN** non-active sibling cards SHALL reduce opacity to 0.5

#### Scenario: Non-clickable card
- **WHEN** the `clickable` prop is false or absent
- **THEN** the card SHALL NOT have hover effects or cursor change
- **THEN** clicking SHALL NOT emit events

### Requirement: SummaryCard value update animation

#### Scenario: Value change animation
- **WHEN** the `value` prop changes
- **THEN** the value element SHALL play a brief scale pulse animation (500ms)
- **THEN** the animation SHALL respect `prefers-reduced-motion`

### Requirement: SummaryCardGroup SHALL provide responsive grid layout

The system SHALL provide a `SummaryCardGroup` component at `shared-ui/components/SummaryCardGroup.vue` as a grid container for `SummaryCard` children.

#### Scenario: Column-based grid
- **WHEN** `SummaryCardGroup` receives `:columns="5"` prop
- **THEN** it SHALL render a CSS grid with `repeat(5, minmax(0, 1fr))` columns and `10px` gap

#### Scenario: Responsive breakpoints
- **WHEN** viewport width is 1000px or below
- **THEN** the grid SHALL switch to `repeat(3, minmax(0, 1fr))`
- **WHEN** viewport width is 768px or below
- **THEN** the grid SHALL switch to `1fr` (single column)

#### Scenario: Auto-fit mode
- **WHEN** `:columns` prop is not provided or set to `"auto"`
- **THEN** the grid SHALL use `repeat(auto-fit, minmax(120px, 1fr))`
