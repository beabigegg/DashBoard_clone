## ADDED Requirements

### Requirement: Shared sortable table composable
The system SHALL provide a `useSortableTable` composable at `shared-composables/useSortableTable.js` for client-side table sorting.

#### Scenario: Sort by string column
- **WHEN** `useSortableTable` is invoked with a string column key and direction `asc`
- **THEN** rows SHALL be sorted alphabetically in ascending order (locale-aware)

#### Scenario: Sort by number column
- **WHEN** `useSortableTable` is invoked with a numeric column key
- **THEN** rows SHALL be sorted numerically (not lexicographically)

#### Scenario: Sort by date column
- **WHEN** `useSortableTable` is invoked with a date column key
- **THEN** rows SHALL be sorted chronologically

#### Scenario: Toggle sort direction
- **WHEN** the user clicks the same column header twice
- **THEN** the sort direction SHALL toggle between `asc` and `desc`

#### Scenario: Sort header accessibility
- **WHEN** a column is sortable
- **THEN** the header cell SHALL include `aria-sort` attribute with value `ascending`, `descending`, or `none`

### Requirement: Pagination control SHALL support page number navigation
The `PaginationControl` component SHALL allow users to jump to specific pages and select page sizes.

#### Scenario: Page number display
- **WHEN** a paginated table has more than 5 pages
- **THEN** the pagination SHALL display a truncated page list (e.g., 1 ... 3 4 5 ... 20)

#### Scenario: Page size selector
- **WHEN** the pagination renders with `showPageSize` enabled
- **THEN** a page size dropdown SHALL be displayed with options 10, 25, 50, 100

#### Scenario: Chinese localization
- **WHEN** the pagination renders
- **THEN** navigation buttons SHALL display "上一頁" and "下一頁" instead of "Prev" and "Next"

#### Scenario: Pagination ARIA labels
- **WHEN** the pagination renders
- **THEN** navigation buttons SHALL have descriptive `aria-label` attributes (e.g., "前往第 3 頁")

#### Scenario: Backward compatibility
- **WHEN** `PaginationControl` is used without new props (`showPageNumbers`, `showPageSize`)
- **THEN** the component SHALL render with existing behavior (Prev/Next only)

### Requirement: Data tables SHALL have zebra striping
Tables within `ui-table-wrap` SHALL display alternating row backgrounds for improved scanability.

#### Scenario: Even row background
- **WHEN** a table renders inside `.ui-table-wrap`
- **THEN** even-numbered `<tbody>` rows SHALL have background color `theme('colors.surface.muted')`

#### Scenario: Global rule placement
- **WHEN** the zebra striping rule is defined
- **THEN** it SHALL be placed in `tailwind.css` `@layer components` under `.ui-table-wrap`

### Requirement: WIP matrix SHALL handle horizontal overflow
The WIP overview matrix container SHALL scroll horizontally when content exceeds the container width.

#### Scenario: Narrow viewport overflow
- **WHEN** the WIP matrix is rendered on a viewport narrower than the matrix width
- **THEN** the matrix container SHALL scroll horizontally instead of overflowing the card boundary

#### Scenario: Theme-scoped rule
- **WHEN** the overflow rule is defined
- **THEN** it SHALL be scoped under `.theme-wip-overview` per CSS contract 4.3
