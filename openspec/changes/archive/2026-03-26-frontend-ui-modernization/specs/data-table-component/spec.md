## ADDED Requirements

### Requirement: DataTable compound component SHALL provide unified table rendering

The system SHALL provide a `DataTable` component at `shared-ui/components/DataTable.vue` that renders a full-featured data table with sorting, pagination, loading, and empty state support. Column definitions SHALL be provided via `DataTableColumn` slot components.

#### Scenario: Basic table rendering
- **WHEN** `DataTable` receives `:data` array and `DataTableColumn` children
- **THEN** it SHALL render a `<table>` with `<thead>` and `<tbody>`
- **THEN** each `DataTableColumn` SHALL produce one `<th>` and corresponding `<td>` per row
- **THEN** the table SHALL apply zebra striping on even rows using `surface.muted` background

#### Scenario: Sticky header on scroll
- **WHEN** the table body overflows its container vertically
- **THEN** the `<thead>` SHALL remain sticky at the top of the scroll container
- **THEN** the sticky header SHALL have `z-index: 10` and a bottom shadow to indicate elevation

#### Scenario: Custom cell rendering via scoped slot
- **WHEN** a `DataTableColumn` provides a `#cell` scoped slot
- **THEN** the cell SHALL render the slot content with `{ row, value, index }` slot props
- **WHEN** no `#cell` slot is provided
- **THEN** the cell SHALL render `row[column.key]` as plain text

### Requirement: DataTable SHALL integrate sorting via useSortableTable

The `DataTable` SHALL integrate the existing `useSortableTable` composable for client-side sorting when the `sortable` prop is set on `DataTableColumn`.

#### Scenario: Sortable column header click
- **WHEN** a user clicks a `DataTableColumn` header with `sortable` prop
- **THEN** the table SHALL sort data by that column in ascending order
- **WHEN** the same header is clicked again
- **THEN** the sort direction SHALL toggle to descending

#### Scenario: Sort indicator display
- **WHEN** a column is the active sort column
- **THEN** the header SHALL display an ascending (▲) or descending (▼) indicator using a Lucide `ArrowUp`/`ArrowDown` icon
- **WHEN** a column is sortable but not the active sort column
- **THEN** the header SHALL display a neutral `ArrowUpDown` icon in muted color

#### Scenario: Server-side sorting mode
- **WHEN** `DataTable` has `:server-sort="true"`
- **THEN** clicking a sortable header SHALL NOT sort data locally
- **THEN** it SHALL emit `@sort` event with `{ key, direction }` payload for the parent to handle

### Requirement: DataTable SHALL integrate pagination

The `DataTable` SHALL render a `PaginationControl` in its footer area when pagination data is provided.

#### Scenario: Pagination display
- **WHEN** `DataTable` receives `:pagination="{ page, perPage, total, totalPages }"` prop
- **THEN** it SHALL render `PaginationControl` below the table body
- **THEN** page change events SHALL emit `@page-change` with the new page number

#### Scenario: No pagination
- **WHEN** the `:pagination` prop is not provided
- **THEN** no pagination footer SHALL be rendered

### Requirement: DataTable SHALL display loading and empty states

#### Scenario: Loading overlay
- **WHEN** `DataTable` has `:loading="true"`
- **THEN** the table body SHALL reduce opacity to 0.4 and disable pointer events
- **THEN** transition SHALL use `var(--motion-normal)` duration

#### Scenario: Empty state with no data
- **WHEN** `:data` array is empty and `:loading` is false
- **THEN** the table SHALL render an `EmptyState` component with `type="no-data"` spanning all columns

#### Scenario: Empty state with filter
- **WHEN** `:data` array is empty, `:loading` is false, and `:empty-type="filter-empty"` is set
- **THEN** the table SHALL render `EmptyState` with `type="filter-empty"`

### Requirement: DataTable SHALL support expandable rows

#### Scenario: Expand row with detail slot
- **WHEN** `DataTable` has a `#expand` scoped slot
- **THEN** each row SHALL have an expand toggle control
- **WHEN** the user clicks the expand toggle
- **THEN** a detail row SHALL appear below spanning all columns, rendering the `#expand` slot with `{ row, index }` props

#### Scenario: Single expand mode
- **WHEN** only one row can be expanded at a time (default behavior)
- **THEN** expanding a new row SHALL collapse the previously expanded row

### Requirement: DataTableColumn SHALL define column configuration

The system SHALL provide a `DataTableColumn` component at `shared-ui/components/DataTableColumn.vue` that defines a single column's configuration.

#### Scenario: Column props
- **WHEN** `DataTableColumn` is used within `DataTable`
- **THEN** it SHALL accept props: `key` (String, required), `label` (String, required), `sortable` (Boolean), `width` (String), `align` (String: 'left'|'center'|'right')
- **THEN** the `key` SHALL be used to extract cell values from row data
