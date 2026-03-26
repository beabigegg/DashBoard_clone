## MODIFIED Requirements

### Requirement: Hold Overview page SHALL display paginated lot details
The page SHALL display a detailed lot table with server-side pagination, preserving scroll position and table layout during page navigation.

#### Scenario: Lot table rendering
- **WHEN** lot data is loaded from `GET /api/hold-overview/lots`
- **THEN** a table SHALL display with 13 columns: LOTID, WORKORDER, QTY, Product, Package, Workcenter, Hold Reason, Spec, Age, Hold By, Dept, Hold Comment, Future Hold Comment
- **THEN** age values SHALL display with "天" suffix

#### Scenario: Lot table responds to all cascade filters
- **WHEN** matrixFilter is `{ workcenter: WC-A, package: PKG-1 }`
- **THEN** lots API SHALL be called with `workcenter=WC-A&package=PKG-1`
- **THEN** only lots matching all active filters SHALL be displayed

#### Scenario: Pagination
- **WHEN** total lots exceeds per_page (50)
- **THEN** Prev/Next buttons and page info SHALL display
- **THEN** page info SHALL show "顯示 {start} - {end} / {total}"

#### Scenario: Page navigation preserves scroll position
- **WHEN** user clicks Next or Prev
- **THEN** data SHALL reload with the updated page number
- **THEN** page scroll position SHALL NOT reset to the top
- **THEN** the table content SHALL remain visible in the DOM during loading
- **THEN** a loading overlay SHALL appear on the table section to indicate progress
- **THEN** summary, matrix, hold pareto, and treemap sections SHALL NOT be refreshed as part of pagination

#### Scenario: Table overlay during pagination
- **WHEN** pagination is in progress
- **THEN** the table rows SHALL be visible but visually dimmed (opacity reduced)
- **THEN** user interaction with table rows SHALL be disabled during loading
- **THEN** once data loads, the overlay SHALL be removed and new rows SHALL display

#### Scenario: Filter changes reset pagination
- **WHEN** any filter changes (filter bar, matrix click, or WIP filter apply)
- **THEN** pagination SHALL reset to page 1

#### Scenario: Empty lot result
- **WHEN** a query returns zero lots
- **THEN** the lot table SHALL display a "No data" placeholder
