## ADDED Requirements

### Requirement: SectionCard SHALL support variant prop

The `SectionCard` component SHALL accept a `variant` prop to control visual appearance.

#### Scenario: Default variant
- **WHEN** `SectionCard` renders without a `variant` prop
- **THEN** it SHALL display with `stroke.soft` border, `surface.card` background, and no shadow (current behavior)

#### Scenario: Elevated variant
- **WHEN** `SectionCard` has `variant="elevated"`
- **THEN** it SHALL display with `shadow-md` box-shadow and no border

#### Scenario: Outlined variant
- **WHEN** `SectionCard` has `variant="outlined"`
- **THEN** it SHALL display with `stroke.soft` border, no shadow, and transparent background

### Requirement: SectionCard SHALL support collapsible mode

#### Scenario: Collapsible header
- **WHEN** `SectionCard` has `:collapsible="true"` and a `#header` slot
- **THEN** the header SHALL display a Lucide `ChevronDown` icon that rotates on toggle
- **THEN** clicking the header SHALL toggle the body visibility with `max-height` transition over `var(--motion-normal)`

#### Scenario: Default collapsed state
- **WHEN** `SectionCard` has `:collapsed="true"` initial prop
- **THEN** the body SHALL be hidden on initial render
