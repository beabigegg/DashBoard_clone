## ADDED Requirements

### Requirement: Report pages SHALL declare a filter strategy class
Each released report page that exposes filter controls SHALL declare whether it is `exploratory` or `monitoring-drilldown` for filter behavior governance.

#### Scenario: Exploratory page classification
- **WHEN** a page is classified as `exploratory`
- **THEN** it SHALL implement interdependent filter options
- **THEN** it SHALL prevent invalid cross-dimension combinations from remaining selectable

#### Scenario: Monitoring/drilldown page classification
- **WHEN** a page is classified as `monitoring-drilldown`
- **THEN** it MAY keep lightweight filters or chart-driven drilldown
- **THEN** it SHALL document why full interdependent options are not required

### Requirement: Exploratory pages SHALL support draft-driven option narrowing
Exploratory pages SHALL update filter option lists according to current draft selections before main query execution.

#### Scenario: Draft change triggers option reload
- **WHEN** user changes any draft filter field that can affect other options
- **THEN** the page SHALL debounce option reload requests
- **THEN** options returned by the latest request SHALL replace prior candidates

#### Scenario: Stale option response protection
- **WHEN** multiple option reload requests are in-flight
- **THEN** only the newest request result SHALL be applied
- **THEN** stale responses SHALL be discarded without mutating UI state

### Requirement: Exploratory pages SHALL prune invalid selected values
Exploratory pages SHALL automatically remove selected values that are no longer valid under the latest upstream draft conditions.

#### Scenario: Upstream change invalidates downstream values
- **WHEN** upstream filters change and previously selected downstream values are absent from narrowed options
- **THEN** those invalid selected values SHALL be removed automatically
- **THEN** the page SHALL keep remaining valid selections unchanged

#### Scenario: Apply query uses pruned committed filters
- **WHEN** user clicks apply/query after pruning occurred
- **THEN** the request SHALL use the current valid filter set only
- **THEN** no removed invalid values SHALL be sent to API parameters

### Requirement: Exploratory pages SHALL keep apply and clear semantics consistent
Exploratory pages SHALL separate draft option narrowing from committed query execution and provide deterministic clear behavior.

#### Scenario: Apply commits current filter state
- **WHEN** user clicks apply/query
- **THEN** all data sections SHALL reload using the same committed filter set
- **THEN** URL state SHALL synchronize with committed filters only

#### Scenario: Clear resets to defaults
- **WHEN** user clicks clear
- **THEN** filters SHALL reset to documented defaults
- **THEN** option candidates SHALL reload for the default state
- **THEN** data sections SHALL reload from the default state
