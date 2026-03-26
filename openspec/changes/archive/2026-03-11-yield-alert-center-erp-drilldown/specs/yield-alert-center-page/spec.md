## ADDED Requirements

### Requirement: Yield Alert Center page SHALL be an independent analysis surface
The page SHALL be implemented as a new tool entry and SHALL NOT alter existing Reject History page behavior.

#### Scenario: Navigation entry
- **WHEN** query/trace tools navigation is rendered
- **THEN** UI SHALL provide a dedicated entry for Yield Alert Center
- **THEN** opening Yield Alert Center SHALL keep existing Reject History routes and interactions unchanged

#### Scenario: Independent filter state
- **WHEN** user changes filters in Yield Alert Center
- **THEN** filter state SHALL be scoped to Yield Alert Center context only
- **THEN** leaving and returning to Reject History SHALL not inherit Yield Alert Center temporary selections

### Requirement: Yield Alert Center page SHALL provide yield trend and alert list views
The page SHALL present both macro trend visibility and actionable alert rows for process engineers.

#### Scenario: Initial query rendering
- **WHEN** user applies a valid date range and dimension filters
- **THEN** page SHALL render yield trend cards/charts from API aggregate response
- **THEN** page SHALL render alert list with pagination and sorting controls

#### Scenario: Alert row context visibility
- **WHEN** alert list is displayed
- **THEN** each row SHALL show `date_bucket`, `workorder`, `reason_code`, `scrap_qty`, `yield_pct`, and `risk_level`
- **THEN** row selection SHALL reveal relevant context fields used to compute the alert

### Requirement: Yield Alert Center page SHALL support drilldown to Reject History context
The page SHALL provide a deterministic jump path from an alert item to Reject History detail context.

#### Scenario: Drilldown with linkage keys
- **WHEN** user clicks drilldown on an alert row
- **THEN** UI SHALL pass at least `date_bucket`, `workorder`, and normalized `reason_code` as linkage context
- **THEN** target Reject History query SHALL execute with those linkage filters pre-applied

#### Scenario: Drilldown with partial match warning
- **WHEN** linkage service reports partial or weak mapping for selected alert row
- **THEN** page SHALL still allow navigation to Reject History
- **THEN** UI SHALL display a visible warning that detail result may be incomplete

### Requirement: Yield Alert Center page SHALL provide resilient feedback states
The page SHALL clearly communicate loading, empty, and error states without blocking retry.

#### Scenario: Loading state
- **WHEN** API query is running
- **THEN** page SHALL show loading indicators for trend and alert regions
- **THEN** repeated submit actions SHALL be throttled or disabled until current request completes

#### Scenario: Error and retry
- **WHEN** API request fails
- **THEN** page SHALL display an error banner with retry action
- **THEN** retry SHALL re-submit the same active filter context
