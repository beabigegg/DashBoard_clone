## MODIFIED Requirements

### Requirement: Reject History page SHALL provide filterable historical query controls
The page SHALL provide a filter area for date range and major production dimensions to drive all report sections, and SHALL provide context-aware option narrowing for exploratory filtering.

#### Scenario: Default filter values
- **WHEN** the page is first loaded
- **THEN** `start_date` and `end_date` SHALL default to a valid recent range
- **THEN** all other dimension filters SHALL default to empty (no restriction)

#### Scenario: Apply and clear filters
- **WHEN** user clicks "查詢"
- **THEN** summary, trend, pareto, and list sections SHALL reload with the same filter set
- **WHEN** user clicks "清除條件"
- **THEN** all filters SHALL reset to defaults and all sections SHALL reload

#### Scenario: Required core filters are present
- **WHEN** the filter panel is rendered
- **THEN** it SHALL include `start_date/end_date` time filter controls
- **THEN** it SHALL include reason filter control
- **THEN** it SHALL include `WORKCENTER_GROUP` filter control

#### Scenario: Draft filter options are interdependent
- **WHEN** user changes draft values for `WORKCENTER_GROUP`, `package`, `reason`, or policy toggles
- **THEN** option candidates for reason/workcenter-group/package SHALL reload under the current draft context
- **THEN** unavailable combinations SHALL NOT remain in selectable options

#### Scenario: Policy toggles affect option scope
- **WHEN** user changes policy toggles (including excluded-scrap and material-scrap switches)
- **THEN** options and query results SHALL use the same policy mode
- **THEN** option narrowing SHALL remain consistent with backend exclusion semantics

#### Scenario: Invalid selected values are pruned
- **WHEN** narrowed options no longer contain previously selected values
- **THEN** invalid selections SHALL be removed automatically before query commit
- **THEN** apply/query SHALL only send valid selected values
