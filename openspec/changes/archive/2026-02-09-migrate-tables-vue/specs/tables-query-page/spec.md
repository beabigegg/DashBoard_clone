## ADDED Requirements

### Requirement: Tables page SHALL display categorized table catalog
The page SHALL display all configured DWH tables as clickable cards, grouped by category.

#### Scenario: Table catalog rendering
- **WHEN** the page loads
- **THEN** the page SHALL fetch table configuration from `GET /api/get_table_info`
- **THEN** tables SHALL be displayed as cards grouped by category (即時數據表, 現況快照表, 歷史累積表, 輔助表)
- **THEN** each card SHALL show the table display name and description

#### Scenario: Large table badge
- **WHEN** a table has `row_count` exceeding 10,000,000
- **THEN** the card SHALL display a visual indicator (badge) marking it as a large table

### Requirement: Tables page SHALL load column metadata on table selection
The page SHALL load and display column information when a table is selected from the catalog.

#### Scenario: Select table from catalog
- **WHEN** user clicks a table card
- **THEN** the page SHALL call `POST /api/get_table_columns` with the table name
- **THEN** the data viewer panel SHALL open showing the table name and column count
- **THEN** a filter input row SHALL appear with one input per column

#### Scenario: Active table indication
- **WHEN** a table is selected
- **THEN** the selected card SHALL have a visual active state
- **THEN** previously active cards SHALL be deactivated

### Requirement: Tables page SHALL support column-level filtering
The page SHALL allow users to enter filter values per column and query the table data.

#### Scenario: Enter filter and query
- **WHEN** user enters filter values in column inputs and clicks "查詢"
- **THEN** the page SHALL call `POST /api/query_table` with the table name, filters, limit (1000), and time_field
- **THEN** the result table SHALL display returned rows with column headers
- **THEN** the title SHALL show the table name, row count, and active filter count

#### Scenario: Enter key triggers query
- **WHEN** user presses Enter in any filter input
- **THEN** the query SHALL execute as if the "查詢" button was clicked

#### Scenario: Active filter display
- **WHEN** filters are applied
- **THEN** active filters SHALL be displayed as removable tags above the result table
- **THEN** clicking a tag's remove button SHALL clear that filter

#### Scenario: Clear all filters
- **WHEN** user clicks "清除篩選"
- **THEN** all filter inputs SHALL be cleared
- **THEN** all active filter tags SHALL be removed

#### Scenario: Query with no filters
- **WHEN** user clicks "查詢" with no filters
- **THEN** the query SHALL return the most recent 1000 rows (sorted by time_field if available)

### Requirement: Tables page SHALL handle loading and error states
The page SHALL display appropriate feedback during API calls and on errors.

#### Scenario: Loading state during column fetch
- **WHEN** column metadata is being fetched
- **THEN** the viewer SHALL display a loading indicator

#### Scenario: Loading state during query
- **WHEN** a query is executing
- **THEN** the table body SHALL display a loading indicator

#### Scenario: API error handling
- **WHEN** an API call fails
- **THEN** the page SHALL display the error message in the relevant area
- **THEN** the page SHALL NOT crash or become unresponsive

#### Scenario: Empty query result
- **WHEN** a query returns zero rows
- **THEN** the table SHALL display a "查無資料" message

### Requirement: Tables page SHALL allow closing the data viewer
The page SHALL allow users to close the data viewer and return to the catalog view.

#### Scenario: Close data viewer
- **WHEN** user clicks the close button on the data viewer
- **THEN** the data viewer panel SHALL be hidden
- **THEN** all table cards SHALL return to inactive state
- **THEN** internal state (columns, filters) SHALL be reset
