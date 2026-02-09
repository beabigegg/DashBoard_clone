## Purpose
Define stable requirements for qc-gate-status-report.

## Requirements


### Requirement: System SHALL provide QC-GATE LOT status API
The system SHALL provide an API endpoint that returns real-time LOT status for all QC-GATE stations, with wait time classification.

#### Scenario: Retrieve QC-GATE summary
- **WHEN** user sends GET `/api/qc-gate/summary`
- **THEN** the system SHALL return all LOTs whose `SPECNAME` contains both "QC" and "GATE" (case-insensitive)
- **THEN** each LOT SHALL include `wait_hours` calculated as `(SYS_DATE - MOVEINTIMESTAMP)` in hours
- **THEN** each LOT SHALL be classified into a time bucket: `lt_6h`, `6h_12h`, `12h_24h`, or `gt_24h`
- **THEN** the response SHALL include per-station bucket counts and the full lot list

#### Scenario: QC-GATE data sourced from WIP cache
- **WHEN** the API is called
- **THEN** the system SHALL read from the existing WIP Redis cache (not direct Oracle query)
- **THEN** the response SHALL include `cache_time` indicating the WIP snapshot timestamp

#### Scenario: No QC-GATE lots in cache
- **WHEN** no LOTs match the QC-GATE SPECNAME pattern
- **THEN** the system SHALL return an empty `stations` array with `cache_time`

### Requirement: QC-GATE stations SHALL be ordered by spec sequence
The system SHALL order QC-GATE stations according to the manufacturing flow sequence from `DW_MES_SPEC_WORKCENTER_V`.

#### Scenario: Station ordering
- **WHEN** the API returns multiple QC-GATE stations
- **THEN** the stations SHALL be sorted by `SPEC_ORDER` from `DW_MES_SPEC_WORKCENTER_V` where `SPEC` matches the SPECNAME

#### Scenario: Station not found in spec dimension table
- **WHEN** a QC-GATE SPECNAME is not found in `DW_MES_SPEC_WORKCENTER_V`
- **THEN** the station SHALL appear at the end of the list with a high default sort order

### Requirement: QC-GATE report page SHALL display stacked bar chart
The page SHALL display a stacked bar chart showing LOT counts per QC-GATE station, grouped by wait time bucket.

#### Scenario: Bar chart rendering
- **WHEN** the page loads and data is available
- **THEN** the X-axis SHALL show QC-GATE station names
- **THEN** the Y-axis SHALL show LOT counts
- **THEN** each bar SHALL be stacked with four color-coded segments: <6hr (green), 6-12hr (yellow), 12-24hr (orange), >24hr (red)

#### Scenario: Empty state
- **WHEN** no QC-GATE LOTs exist
- **THEN** the chart area SHALL display a "目前無 QC-GATE LOT" message

### Requirement: QC-GATE report page SHALL display filterable LOT table
The page SHALL display a table listing individual LOTs, with click-to-filter interaction from the bar chart.

#### Scenario: Default table display
- **WHEN** the page loads
- **THEN** the table SHALL show all QC-GATE LOTs sorted by wait time descending

#### Scenario: Click bar chart to filter
- **WHEN** user clicks a specific segment of a bar (e.g., QC-GATE-DB's 6-12hr segment)
- **THEN** the table SHALL filter to show only LOTs matching that station AND time bucket
- **THEN** a filter indicator SHALL be visible showing the active filter

#### Scenario: Clear filter
- **WHEN** user clicks the active filter indicator or clicks the same bar segment again
- **THEN** the table SHALL return to showing all QC-GATE LOTs

### Requirement: QC-GATE report page SHALL auto-refresh
The page SHALL automatically refresh data at the same interval as the WIP cache update cycle.

#### Scenario: Auto-refresh while visible
- **WHEN** the page is visible and 10 minutes have elapsed since last refresh
- **THEN** the page SHALL fetch new data from the API without showing a full loading overlay
- **THEN** the chart and table SHALL update with new data

#### Scenario: Auto-refresh while hidden
- **WHEN** the page tab/iframe is hidden (document.hidden === true)
- **THEN** the auto-refresh SHALL be skipped

#### Scenario: Page becomes visible after being hidden
- **WHEN** the page becomes visible after being hidden
- **THEN** the page SHALL immediately refresh data

#### Scenario: Manual refresh
- **WHEN** user clicks the refresh button
- **THEN** the page SHALL fetch new data and reset the auto-refresh timer
