## ADDED Requirements

### Requirement: Hold History page SHALL display a filter bar with date range and hold type
The page SHALL provide a filter bar for selecting date range and hold type classification.

#### Scenario: Default date range
- **WHEN** the page loads
- **THEN** the date range SHALL default to the first and last day of the current month

#### Scenario: Hold Type radio default
- **WHEN** the page loads
- **THEN** the Hold Type filter SHALL default to "品質異常"
- **THEN** three radio options SHALL display: 品質異常, 非品質異常, 全部

#### Scenario: Filter bar change reloads all data
- **WHEN** user changes the date range or Hold Type selection
- **THEN** all API calls (trend, reason-pareto, duration, department, list) SHALL reload with the new parameters
- **THEN** any active Reason Pareto filter SHALL be cleared
- **THEN** pagination SHALL reset to page 1

### Requirement: Hold History page SHALL display summary KPI cards
The page SHALL show 6 summary KPI cards derived from the trend data for the selected period.

#### Scenario: Summary cards rendering
- **WHEN** trend data is loaded
- **THEN** six cards SHALL display: Release 數量, New Hold 數量, Future Hold 數量, 淨變動, 期末 On Hold, 平均 Hold 時長
- **THEN** Release SHALL be displayed as a positive indicator (green)
- **THEN** New Hold and Future Hold SHALL be displayed as negative indicators (red/orange)
- **THEN** 淨變動 SHALL equal Release - New Hold - Future Hold
- **THEN** 期末 On Hold SHALL be the HOLDQTY of the last day in the selected range
- **THEN** number values SHALL use zh-TW number formatting

#### Scenario: Summary reflects filter bar only
- **WHEN** user clicks a Reason Pareto block
- **THEN** summary cards SHALL NOT change (they only respond to filter bar changes)

### Requirement: Hold History page SHALL display a Daily Trend chart
The page SHALL display a mixed line+bar chart showing daily hold stock and flow.

#### Scenario: Daily Trend chart rendering
- **WHEN** trend data is loaded
- **THEN** an ECharts mixed chart SHALL display with dual Y-axes
- **THEN** the left Y-axis SHALL show flow quantities (Release, New Hold, Future Hold)
- **THEN** the right Y-axis SHALL show HOLDQTY stock level
- **THEN** the X-axis SHALL show dates within the selected range

#### Scenario: Bar direction encoding
- **WHEN** daily trend bars are rendered
- **THEN** Release bars SHALL extend upward (positive direction, green color)
- **THEN** New Hold bars SHALL extend downward (negative direction, red color)
- **THEN** Future Hold bars SHALL extend downward (negative direction, orange color, stacked with New Hold)
- **THEN** HOLDQTY SHALL display as a line on the right Y-axis

#### Scenario: Hold Type switching without re-call
- **WHEN** user changes the Hold Type radio on the filter bar
- **THEN** if the date range has not changed, the trend chart SHALL update from locally cached data
- **THEN** no additional API call SHALL be made for the trend endpoint

#### Scenario: Daily Trend reflects filter bar only
- **WHEN** user clicks a Reason Pareto block
- **THEN** the Daily Trend chart SHALL NOT change (it only responds to filter bar changes)

### Requirement: Hold History page SHALL display a Reason Pareto chart
The page SHALL display a Pareto chart showing hold reason distribution.

#### Scenario: Reason Pareto rendering
- **WHEN** reason-pareto data is loaded
- **THEN** a Pareto chart SHALL display with bars (count per reason) and a cumulative percentage line
- **THEN** reasons SHALL be sorted by count descending
- **THEN** the cumulative line SHALL reach 100% at the rightmost bar

#### Scenario: Reason Pareto click filters downstream
- **WHEN** user clicks a reason bar in the Pareto chart
- **THEN** `reasonFilter` SHALL be set to the clicked reason name
- **THEN** Department table SHALL reload filtered by that reason
- **THEN** Detail table SHALL reload filtered by that reason
- **THEN** the clicked bar SHALL show a visual highlight

#### Scenario: Reason Pareto click toggle
- **WHEN** user clicks the same reason bar that is already active
- **THEN** `reasonFilter` SHALL be cleared
- **THEN** Department table and Detail table SHALL reload without reason filter

#### Scenario: Reason Pareto reflects filter bar only
- **WHEN** user clicks a reason bar
- **THEN** Summary KPIs, Daily Trend, and Duration chart SHALL NOT change

### Requirement: Hold History page SHALL display Hold Duration distribution
The page SHALL display a horizontal bar chart showing hold duration distribution.

#### Scenario: Duration chart rendering
- **WHEN** duration data is loaded
- **THEN** a horizontal bar chart SHALL display with 4 buckets: <4h, 4-24h, 1-3天, >3天
- **THEN** each bar SHALL show count and percentage
- **THEN** only released holds (RELEASETXNDATE IS NOT NULL) SHALL be included

#### Scenario: Duration reflects filter bar only
- **WHEN** user clicks a Reason Pareto block
- **THEN** the Duration chart SHALL NOT change (it only responds to filter bar changes)

### Requirement: Hold History page SHALL display Department statistics with expandable rows
The page SHALL display a table showing hold/release statistics per department, expandable to show individual persons.

#### Scenario: Department table rendering
- **WHEN** department data is loaded
- **THEN** a table SHALL display with columns: 部門, Hold 次數, Release 次數, 平均 Hold 時長(hr)
- **THEN** departments SHALL be sorted by Hold 次數 descending
- **THEN** each department row SHALL have an expand toggle

#### Scenario: Department row expansion
- **WHEN** user clicks the expand toggle on a department row
- **THEN** individual person rows SHALL display below the department row
- **THEN** person rows SHALL show: 人員名稱, Hold 次數, Release 次數, 平均 Hold 時長(hr)

#### Scenario: Department table responds to reason filter
- **WHEN** a Reason Pareto filter is active
- **THEN** department data SHALL reload filtered by the selected reason
- **THEN** only holds matching the reason SHALL be included in statistics

### Requirement: Hold History page SHALL display paginated Hold/Release detail list
The page SHALL display a detailed list of individual hold/release records with server-side pagination.

#### Scenario: Detail table columns
- **WHEN** detail data is loaded
- **THEN** a table SHALL display with columns: Lot ID, WorkOrder, 站別, Hold Reason, Hold 時間, Hold 人員, Hold Comment, Release 時間, Release 人員, Release Comment, 時長(hr), NCR

#### Scenario: Unreleased hold display
- **WHEN** a hold record has RELEASETXNDATE IS NULL
- **THEN** the Release 時間 column SHALL display "仍在 Hold"
- **THEN** the 時長 column SHALL display the duration from HOLDTXNDATE to current time

#### Scenario: Detail table pagination
- **WHEN** total records exceed per_page (50)
- **THEN** Prev/Next buttons and page info SHALL display
- **THEN** page info SHALL show "顯示 {start} - {end} / {total}"

#### Scenario: Detail table responds to reason filter
- **WHEN** a Reason Pareto filter is active
- **THEN** detail data SHALL reload filtered by the selected reason
- **THEN** pagination SHALL reset to page 1

#### Scenario: Filter changes reset pagination
- **WHEN** any filter changes (filter bar or Reason Pareto click)
- **THEN** pagination SHALL reset to page 1

### Requirement: Hold History page SHALL display active filter indicator
The page SHALL show a clear indicator when a Reason Pareto filter is active.

#### Scenario: Reason filter indicator
- **WHEN** a reason filter is active
- **THEN** a filter indicator SHALL display above the Department table section
- **THEN** the indicator SHALL show the active reason name
- **THEN** a clear button (✕) SHALL remove the reason filter

### Requirement: Hold History page SHALL handle loading and error states
The page SHALL display appropriate feedback during API calls and on errors.

#### Scenario: Initial loading overlay
- **WHEN** the page first loads
- **THEN** a full-page loading overlay SHALL display until all data is loaded

#### Scenario: API error handling
- **WHEN** an API call fails
- **THEN** an error banner SHALL display with the error message
- **THEN** the page SHALL NOT crash or become unresponsive

### Requirement: Hold History page SHALL have navigation links
The page SHALL provide navigation to related pages.

#### Scenario: Back to Hold Overview
- **WHEN** user clicks the "← Hold Overview" button in the header
- **THEN** the page SHALL navigate to `/hold-overview`
