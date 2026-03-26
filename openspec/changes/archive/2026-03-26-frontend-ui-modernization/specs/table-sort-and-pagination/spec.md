## ADDED Requirements

### Requirement: DataTable SHALL encapsulate useSortableTable and PaginationControl

The `DataTable` component SHALL internally integrate `useSortableTable` composable and `PaginationControl` component so that consuming features do not need to wire these separately.

#### Scenario: Internal sort integration
- **WHEN** `DataTable` has sortable columns and `:server-sort` is false (default)
- **THEN** it SHALL internally call `useSortableTable(data)` and render `sortedData`
- **THEN** the parent component SHALL NOT need to import or configure `useSortableTable`

#### Scenario: Internal pagination integration
- **WHEN** `DataTable` receives `:pagination` prop
- **THEN** it SHALL internally render `PaginationControl` in the table footer
- **THEN** the parent component SHALL only handle the `@page-change` event to fetch new data

#### Scenario: Sort indicator icons
- **WHEN** a sortable column header is rendered
- **THEN** the sort indicator SHALL use Lucide icons (`ArrowUp`, `ArrowDown`, `ArrowUpDown`) instead of Unicode characters (▲, ▼, ⇕)
