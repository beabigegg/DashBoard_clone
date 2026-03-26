## ADDED Requirements

### Requirement: Feature pages SHALL adopt shared-ui components for table rendering

All in-scope feature pages that display tabular data SHALL migrate from custom table markup to the `DataTable` component.

#### Scenario: Batch 1 table migration (wip-overview, hold-overview, resource-status)
- **WHEN** wip-overview, hold-overview, or resource-status render detail/list tables
- **THEN** they SHALL use `DataTable` with `DataTableColumn` slot-based column definitions
- **THEN** sorting indicators, pagination, loading overlay, and empty state SHALL come from DataTable built-in behavior

#### Scenario: Batch 2 table migration (hold-detail, wip-detail, reject-history)
- **WHEN** hold-detail, wip-detail, or reject-history render detail tables
- **THEN** they SHALL use `DataTable` with custom `#cell` and `#expand` slots where needed
- **THEN** reject-history expandable breakdown rows SHALL use the `#expand` slot

#### Scenario: Matrix tables exemption
- **WHEN** wip-overview or hold-overview render matrix/cross-tab tables
- **THEN** they SHALL keep their dedicated MatrixTable/HoldMatrix components
- **THEN** MatrixTable components SHALL adopt DataTable's loading overlay and empty state patterns

### Requirement: Feature pages SHALL adopt SummaryCard for KPI display

All in-scope feature pages that display summary/KPI cards SHALL migrate to `SummaryCard` and `SummaryCardGroup`.

#### Scenario: Summary card migration
- **WHEN** a feature page currently renders `.summary-card` HTML with custom markup
- **THEN** it SHALL be replaced with `<SummaryCard>` component usage
- **THEN** accent colors SHALL map current status classes (`.prd`, `.sby`, etc.) to `accent` prop values

#### Scenario: Interactive summary cards preservation
- **WHEN** resource-status or wip-detail summary cards are clickable filters
- **THEN** the migrated `<SummaryCard>` SHALL use `clickable` and `active` props to preserve the same interaction

### Requirement: Feature pages SHALL use shared-ui components for common UI patterns

#### Scenario: PageHeader adoption
- **WHEN** a feature page renders a page header
- **THEN** it SHALL use the `PageHeader` shared-ui component
- **THEN** custom `.header-gradient` markup SHALL be removed from the feature

#### Scenario: EmptyState adoption
- **WHEN** a feature page displays a no-data or error state
- **THEN** it SHALL use the `EmptyState` shared-ui component instead of custom empty state markup

#### Scenario: ErrorBanner adoption
- **WHEN** a feature page displays an error message banner
- **THEN** it SHALL use the `ErrorBanner` shared-ui component

### Requirement: Feature CSS SHALL be reduced after component adoption

#### Scenario: Duplicate style removal
- **WHEN** a feature page adopts a shared-ui component
- **THEN** the corresponding duplicate CSS classes in the feature's `style.css` SHALL be removed
- **THEN** only theme-specific overrides that cannot be handled by component props SHALL remain

#### Scenario: CSS inventory update
- **WHEN** feature CSS files are modified during migration
- **THEN** `contract/css_inventory.md` SHALL be updated to reflect any file additions, removals, or scope changes

### Requirement: Feature page unification SHALL follow batched rollout

#### Scenario: Batch independence
- **WHEN** a batch of features is migrated
- **THEN** each batch SHALL be independently deployable and revertable
- **THEN** later batches SHALL NOT depend on earlier batches being complete

#### Scenario: Batch 3-6 scope
- **WHEN** Batch 3 (resource-history, hold-history, qc-gate), Batch 4 (query-tool, material-trace, yield-alert-center), Batch 5 (job-query, tables, excel-query, mid-section-defect), or Batch 6 (admin-dashboard, anomaly-overview, production-history) is executed
- **THEN** they SHALL follow the same migration patterns established in Batch 1-2

#### Scenario: In-scope native route coverage completeness
- **WHEN** feature page unification scope is finalized
- **THEN** all 19 in-scope native routes in route contracts SHALL be explicitly assigned to one of Batch 1-6
- **THEN** deprecated direct-entry admin routes (`/admin/performance`, `/admin/user-usage-kpi`) SHALL be excluded from migration targets and treated as redirect compatibility checks
