## ADDED Requirements

### Requirement: TimelineChart component SHALL render configurable Gantt-style timelines
A shared `TimelineChart` component SHALL accept structured track/event data and render a horizontal timeline with SVG/CSS.

#### Scenario: Basic track rendering
- **WHEN** TimelineChart receives tracks with bars (each bar having start time, end time, type)
- **THEN** it SHALL render a horizontal time axis and one row per track
- **THEN** each bar SHALL be positioned proportionally along the time axis with width reflecting duration

#### Scenario: Color mapping
- **WHEN** bars have different `type` values
- **THEN** each type SHALL be rendered with a color from the provided `colorMap` prop
- **THEN** a legend SHALL be displayed showing type-to-color mapping

#### Scenario: Event markers
- **WHEN** the component receives events (point-in-time markers)
- **THEN** each event SHALL render as a marker (diamond/triangle icon) at the corresponding time position on its track
- **THEN** hovering over a marker SHALL display a tooltip with the event label and details

#### Scenario: Time axis adapts to data range
- **WHEN** the timeline data spans hours
- **THEN** the time axis SHALL show hour ticks (e.g., 06:00, 07:00, ...)
- **WHEN** the timeline data spans days
- **THEN** the time axis SHALL show date ticks (e.g., 02-10, 02-11, ...)

#### Scenario: Horizontal scroll for long timelines
- **WHEN** the timeline data exceeds the visible width
- **THEN** the component SHALL support horizontal scrolling
- **THEN** track labels on the left SHALL remain fixed (sticky) during scroll

#### Scenario: Bar tooltip on hover
- **WHEN** the user hovers over a bar segment
- **THEN** a tooltip SHALL display the bar's label, start time, end time, and duration

### Requirement: TimelineChart SHALL support multi-layer overlapping tracks
The component SHALL support rendering multiple bar layers on a single track row (e.g., status bars behind lot bars).

#### Scenario: Overlapping layers
- **WHEN** a track has multiple layers (e.g., `statusBars` and `lotBars`)
- **THEN** background layer bars SHALL render behind foreground layer bars
- **THEN** both layers SHALL be visible (foreground bars shorter in height or semi-transparent)

### Requirement: TimelineChart SHALL have no external charting dependencies
The component SHALL be implemented using only SVG elements and CSS, with no external charting library.

#### Scenario: Zero additional dependencies
- **WHEN** the TimelineChart component is used
- **THEN** it SHALL NOT require any npm package not already in the project
- **THEN** rendering SHALL use inline SVG elements within the Vue template
