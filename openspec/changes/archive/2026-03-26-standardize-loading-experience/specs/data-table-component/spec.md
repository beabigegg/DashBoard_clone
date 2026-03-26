## MODIFIED Requirements

### Requirement: DataTable SHALL display loading and empty states

`DataTable` SHALL handle both loading and empty states through its own `:loading` prop and `EmptyState` integration. Features MUST NOT introduce separate ad hoc loading placeholders for the same tabular state.

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

#### Scenario: Table loading consistency over custom placeholders
- **WHEN** a feature page uses `DataTable` for tabular content
- **THEN** loading visuals SHALL come from `DataTable :loading` behavior instead of separate ad hoc table-loading placeholders for the same state
