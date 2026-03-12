## MODIFIED Requirements

### Requirement: Detail page SHALL support server-side pagination
The page SHALL paginate lot data with server-side support, preserving scroll position and table layout during page navigation.

#### Scenario: Pagination controls
- **WHEN** total pages exceeds 1
- **THEN** Prev/Next buttons and page info SHALL display
- **THEN** Prev SHALL be disabled on page 1
- **THEN** Next SHALL be disabled on the last page

#### Scenario: Page navigation preserves scroll position
- **WHEN** user clicks Next or Prev
- **THEN** data SHALL reload with the updated page number
- **THEN** page scroll position SHALL NOT reset to the top
- **THEN** the table content SHALL remain visible in the DOM during loading
- **THEN** a loading overlay SHALL appear on the table section to indicate progress
- **THEN** SummaryCards SHALL NOT be refreshed as part of pagination

#### Scenario: Table overlay during pagination
- **WHEN** pagination is in progress
- **THEN** the table rows SHALL be visible but visually dimmed (opacity reduced)
- **THEN** user interaction with table rows SHALL be disabled during loading
- **THEN** once data loads, the overlay SHALL be removed and new rows SHALL display
