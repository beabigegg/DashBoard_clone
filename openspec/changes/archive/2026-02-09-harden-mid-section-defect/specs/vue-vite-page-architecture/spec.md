## ADDED Requirements

### Requirement: Mid-section defect page SHALL separate filter state from query state
The mid-section defect page SHALL maintain separate reactive state for UI input (`filters`) and committed query parameters (`committedFilters`).

#### Scenario: User changes date without clicking query
- **WHEN** user modifies the date range in the filter bar but does not click "查詢"
- **THEN** auto-refresh, pagination, and CSV export SHALL continue using the previously committed filter values
- **THEN** the new date range SHALL NOT affect any API calls until "查詢" is clicked

#### Scenario: User clicks query button
- **WHEN** user clicks "查詢"
- **THEN** the current `filters` state SHALL be snapshotted into `committedFilters`
- **THEN** all subsequent API calls SHALL use the committed values

#### Scenario: CSV export uses committed filters
- **WHEN** user clicks "匯出 CSV" after modifying filters without re-querying
- **THEN** the export SHALL use the committed filter values from the last query
- **THEN** the export SHALL NOT use the current UI filter values

### Requirement: Mid-section defect page SHALL cancel in-flight requests on new query
The mid-section defect page SHALL use `AbortController` to cancel in-flight API requests when a new query is initiated.

#### Scenario: New query cancels previous query
- **WHEN** user clicks "查詢" while a previous query is still in-flight
- **THEN** the previous query's summary and detail requests SHALL be aborted
- **THEN** the AbortError SHALL be handled silently (no error banner shown)

#### Scenario: Page navigation cancels previous detail request
- **WHEN** user clicks next page while a previous page request is still in-flight
- **THEN** the previous page request SHALL be aborted
- **THEN** the new page request SHALL proceed independently

#### Scenario: Query and pagination use independent abort keys
- **WHEN** a query is in-flight and user triggers pagination
- **THEN** the query SHALL NOT be cancelled by the pagination request
- **THEN** the pagination SHALL use a separate abort key from the query
