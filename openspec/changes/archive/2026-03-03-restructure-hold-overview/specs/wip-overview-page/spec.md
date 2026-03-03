## MODIFIED Requirements

### Requirement: Overview page SHALL display WIP status breakdown cards
The page SHALL display four clickable status cards (RUN, QUEUE, 品質異常, 非品質異常) with lot and quantity counts.

#### Scenario: Status cards rendering
- **WHEN** summary data is loaded
- **THEN** four status cards SHALL be displayed with color coding (green=RUN, yellow=QUEUE, red=品質異常, orange=非品質異常)
- **THEN** each card SHALL show lot count and quantity

#### Scenario: RUN/QUEUE card click filters matrix
- **WHEN** user clicks the RUN or QUEUE status card
- **THEN** the matrix table SHALL reload with the selected status filter
- **THEN** the clicked card SHALL show an active visual state
- **THEN** clicking the same card again SHALL deactivate the filter and restore all cards
- **THEN** the URL SHALL be updated to reflect the active status filter

#### Scenario: Hold card click navigates to Hold Overview
- **WHEN** user clicks the "品質異常" status card
- **THEN** the page SHALL navigate to `/hold-overview?hold_type=quality`
- **WHEN** user clicks the "非品質異常" status card
- **THEN** the page SHALL navigate to `/hold-overview?hold_type=non-quality`

## REMOVED Requirements

### Requirement: Overview page SHALL display Hold Pareto analysis
**Reason**: Hold Pareto charts are moved to the Hold Overview page where they are more relevant.
**Migration**: Users can access the same Pareto analysis on the Hold Overview page. Clicking the "品質異常" or "非品質異常" status cards navigates directly there.
