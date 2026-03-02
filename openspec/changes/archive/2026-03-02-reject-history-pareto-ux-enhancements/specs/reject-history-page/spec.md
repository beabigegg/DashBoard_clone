## MODIFIED Requirements

### Requirement: Reject History page SHALL provide reason Pareto analysis
The page SHALL provide a Pareto view for loss reasons and support downstream filtering.

#### Scenario: Pareto rendering and ordering
- **WHEN** Pareto data is loaded
- **THEN** items SHALL be sorted by selected metric descending
- **THEN** a cumulative percentage line SHALL be shown

#### Scenario: Pareto 80% filter is managed in supplementary filters
- **WHEN** the page first loads Pareto
- **THEN** supplementary filters SHALL include "Pareto 僅顯示累計前 80%" control
- **THEN** the control SHALL default to enabled

#### Scenario: TYPE/WORKFLOW/機台 support display scope selector
- **WHEN** Pareto dimension is `TYPE`, `WORKFLOW`, or `機台`
- **THEN** the UI SHALL provide `全部顯示` and `只顯示 TOP 20` options
- **THEN** `全部顯示` SHALL still respect the current 80% cumulative filter setting

#### Scenario: Pareto click filtering supports multi-select
- **WHEN** user clicks Pareto bars or table rows
- **THEN** clicked items SHALL become active selected chips
- **THEN** multiple selected items SHALL be supported at the same time
- **THEN** detail list SHALL reload using current selected Pareto items as additional filter criteria

#### Scenario: Re-click clears selected item only
- **WHEN** user clicks an already selected Pareto item
- **THEN** only that item SHALL be removed from selection
- **THEN** remaining selected items SHALL stay active

### Requirement: Reject History page SHALL support CSV export from current filter context
The page SHALL allow users to export records using the exact active filters.

#### Scenario: Export with all active filters
- **WHEN** user clicks "匯出 CSV"
- **THEN** export request SHALL include current primary filters, supplementary filters, trend-date filters, metric filters, and Pareto-selected items
- **THEN** downloaded file SHALL contain exactly the same rows currently represented by the detail list filter context

#### Scenario: Export remains UTF-8 Excel compatible
- **WHEN** CSV export is downloaded
- **THEN** the file SHALL be encoded in UTF-8 with BOM
- **THEN** Chinese headers and values SHALL render correctly in common spreadsheet tools
