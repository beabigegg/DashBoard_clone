## ADDED Requirements

### Requirement: HoldLotTable SHALL support column sorting

The shared `wip-shared/HoldLotTable.vue` component SHALL allow users to sort data by clicking column headers.

#### Scenario: Click column header to sort ascending
- **WHEN** the user clicks a column header that is not currently sorted
- **THEN** the table SHALL sort by that column in ascending order
- **THEN** the header SHALL display ▲ indicator

#### Scenario: Click same column to toggle direction
- **WHEN** the user clicks a column header that is already sorted ascending
- **THEN** the sort direction SHALL toggle to descending
- **THEN** the header SHALL display ▼ indicator

#### Scenario: Unsorted column shows neutral indicator
- **WHEN** a column is not the active sort column
- **THEN** the header SHALL display ⇕ indicator

#### Scenario: All 13 columns are sortable
- **GIVEN** the table has columns: LOTID, WORKORDER, QTY, Product, Package, Workcenter, Hold Reason, Spec, Age, Hold By, Dept, Hold Comment, Future Hold Comment
- **THEN** all 13 columns SHALL be sortable via header click

#### Scenario: Sort is client-side on current page data
- **WHEN** the user sorts a column
- **THEN** only the current page's data SHALL be reordered
- **THEN** no additional API calls SHALL be made

#### Scenario: Accessibility via aria-sort
- **WHEN** a column is sorted
- **THEN** the `<th>` element SHALL have `aria-sort="ascending"` or `aria-sort="descending"`
- **WHEN** a column is not sorted
- **THEN** the `<th>` element SHALL have `aria-sort="none"`
