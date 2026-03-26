## ADDED Requirements

### Requirement: Chip component SHALL visually harmonize with ui-btn system

#### Scenario: Chip and button visual consistency
- **WHEN** a `Chip` component renders alongside `ui-btn` elements
- **THEN** the chip SHALL use the same `font-family`, `font-weight` (500 vs btn's 600), and motion tokens (`--motion-fast` hover transition)
- **THEN** the chip's `border-radius: pill` SHALL visually distinguish it from buttons' `border-radius: button`

#### Scenario: Chip disabled state
- **WHEN** a `Chip` has `:disabled="true"`
- **THEN** it SHALL apply `opacity: 0.6` and `cursor: not-allowed`, consistent with `.ui-btn:disabled` behavior
