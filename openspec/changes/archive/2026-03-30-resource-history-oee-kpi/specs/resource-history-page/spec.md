## MODIFIED Requirements

### Requirement: Resource History page SHALL display KPI summary cards
The page SHALL show 10 KPI cards with aggregated performance metrics derived from the cached dataset, including OEE%.

#### Scenario: KPI cards from cached data
- **WHEN** summary data is derived from the cached DataFrame
- **THEN** 10 cards SHALL display in order: OU%, OEE%, AVAIL%, PRD, SBY, UDT, SDT, EGT, NST, Machine Count
- **THEN** the OEE% card SHALL show the computed OEE percentage
- **THEN** the OEE% card SHALL use accent coloring consistent with the OU% card logic
- **THEN** values SHALL be computed from the cached shift-status records combined with OEE production/NG data

### Requirement: Resource History page SHALL display hierarchical detail table
The page SHALL show a three-level expandable table derived from the cached dataset, including OEE% column.

#### Scenario: Detail table from cached data
- **WHEN** detail data is derived from the cached DataFrame
- **THEN** a tree table SHALL display with existing columns plus an OEE% column
- **THEN** OEE% column SHALL appear between OU% and AVAIL% columns
- **THEN** each row SHALL show the OEE% computed from that resource's availability and yield data
- **THEN** if a resource has no production data (trackout + ng = 0), OEE% SHALL display as "—"

## ADDED Requirements

### Requirement: Resource History trend chart SHALL overlay OEE% line
The trend chart SHALL display an OEE% line alongside existing OU% and AVAIL% lines.

#### Scenario: OEE% trend line rendering
- **WHEN** trend data includes OEE metrics per period
- **THEN** the chart SHALL render an OEE% line with a distinct color from OU% and AVAIL%
- **THEN** the OEE% line SHALL use the same Y-axis scale (0-100%) as other percentage lines
- **THEN** the legend SHALL include an OEE% entry

### Requirement: Resource History heatmap SHALL support metric toggle
The heatmap SHALL allow switching between OU%, OEE%, and AVAIL% metrics.

#### Scenario: Heatmap metric selection
- **WHEN** user selects a different metric from the heatmap dropdown
- **THEN** the heatmap cells SHALL recalculate using the selected metric
- **THEN** the color scale SHALL adjust to the selected metric's value range
- **THEN** the default metric SHALL be OU%
- **THEN** no additional API call SHALL be made — data for all metrics SHALL be present in the existing response

### Requirement: CSV export SHALL include OEE% column
The CSV export SHALL include OEE-related fields alongside existing columns.

#### Scenario: Export with OEE data
- **WHEN** user exports resource history data to CSV
- **THEN** the CSV SHALL include columns: `OEE%`, `Yield%`, `TRACKOUT_QTY`, `NG_QTY`
- **THEN** OEE% SHALL appear between OU% and AVAIL%, followed by Yield%, TRACKOUT_QTY, NG_QTY after AVAIL% (matching the KPI card and detail table column order)
