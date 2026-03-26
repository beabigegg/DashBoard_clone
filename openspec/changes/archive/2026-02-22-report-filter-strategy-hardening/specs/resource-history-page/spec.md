## MODIFIED Requirements

### Requirement: Resource History page SHALL support multi-select filtering
The page SHALL provide multi-select dropdown filters for workcenter groups and families, and SHALL support interdependent narrowing with machine options and selected-value pruning.

#### Scenario: Multi-select dropdown
- **WHEN** user clicks a multi-select dropdown trigger
- **THEN** a dropdown SHALL display with checkboxes for each option
- **THEN** "Select All" and "Clear All" buttons SHALL be available
- **THEN** clicking outside the dropdown SHALL close it

#### Scenario: Filter options loading
- **WHEN** the page loads
- **THEN** workcenter groups and families SHALL load from `GET /api/resource/history/options`
- **THEN** machine candidates SHALL be derivable before first query from loaded option resources

#### Scenario: Upstream filters narrow downstream options
- **WHEN** user changes upstream filters (`workcenterGroups`, `families`, equipment-type flags)
- **THEN** machine options SHALL be recomputed to only include matching resources
- **THEN** narrowed options SHALL be reflected immediately in filter controls

#### Scenario: Invalid selected machines are pruned
- **WHEN** upstream filters change and selected machines are no longer valid
- **THEN** invalid selected machine values SHALL be removed automatically
- **THEN** remaining valid selected machine values SHALL be preserved

#### Scenario: Equipment type checkboxes
- **WHEN** user toggles a checkbox (生產設備, 重點設備, 監控設備)
- **THEN** the next query SHALL include the corresponding filter parameter
- **THEN** option narrowing SHALL also honor the same checkbox conditions
