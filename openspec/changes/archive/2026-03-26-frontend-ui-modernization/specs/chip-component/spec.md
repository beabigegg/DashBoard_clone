## ADDED Requirements

### Requirement: Chip component SHALL provide unified tag/chip rendering

The system SHALL provide a `Chip` component at `shared-ui/components/Chip.vue` for displaying filter chips, status tags, and removable selections.

#### Scenario: Basic chip rendering
- **WHEN** `Chip` receives a `label` prop or default slot content
- **THEN** it SHALL render a pill-shaped element (border-radius `pill`) with 4px 10px padding
- **THEN** font size SHALL be 12px with font-weight 500

#### Scenario: Tone variants
- **WHEN** `tone` prop is one of: `neutral`, `brand`, `success`, `warning`, `danger`, `info`
- **THEN** the chip background and text color SHALL map to the corresponding state token colors
- **WHEN** `tone` is not provided
- **THEN** it SHALL default to `neutral`

#### Scenario: Removable chip
- **WHEN** the `removable` prop is true
- **THEN** the chip SHALL display a Lucide `X` icon (12px) at the right side
- **WHEN** the user clicks the remove icon
- **THEN** the chip SHALL emit a `@remove` event

#### Scenario: Clickable chip
- **WHEN** the `clickable` prop is true
- **THEN** the chip SHALL have `cursor: pointer` and hover background transition
- **THEN** clicking SHALL emit a `@click` event

#### Scenario: Icon slot
- **WHEN** a `#icon` slot is provided
- **THEN** it SHALL render at the left side of the label with 4px gap
