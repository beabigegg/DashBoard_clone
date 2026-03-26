## MODIFIED Requirements

### Requirement: System SHALL provide QC-GATE LOT status API
The system SHALL provide an API endpoint that returns real-time LOT status for all QC-GATE stations, with wait time classification.

#### Scenario: Retrieve QC-GATE summary
- **WHEN** user sends GET `/api/qc-gate/summary`
- **THEN** the system SHALL return all LOTs whose `SPECNAME` contains both "QC" and "GATE" (case-insensitive)
- **THEN** each LOT SHALL include `wait_hours` calculated as `(SYS_DATE - MOVEINTIMESTAMP)` in hours
- **THEN** each LOT SHALL be classified into a time bucket: `lt_6h`, `6h_12h`, `12h_24h`, or `gt_24h`
- **THEN** each LOT SHALL include a `package` field sourced from the `PACKAGE_LEF` column of `DW_MES_LOT_V`
- **THEN** the response SHALL include per-station bucket counts and the full lot list

#### Scenario: QC-GATE data sourced from WIP cache
- **WHEN** the API is called
- **THEN** the system SHALL read from the existing WIP Redis cache (not direct Oracle query)
- **THEN** the response SHALL include `cache_time` indicating the WIP snapshot timestamp

#### Scenario: No QC-GATE lots in cache
- **WHEN** no LOTs match the QC-GATE SPECNAME pattern
- **THEN** the system SHALL return an empty `stations` array with `cache_time`

### Requirement: QC-GATE report page SHALL display filterable LOT table
The page SHALL display a table listing individual LOTs, with click-to-filter interaction from the bar chart.

#### Scenario: Default table display
- **WHEN** the page loads
- **THEN** the table SHALL show all QC-GATE LOTs sorted by wait time descending
- **THEN** the table SHALL display a "Package" column immediately after the "LOT ID" column

#### Scenario: Package column displays PACKAGE_LEF value
- **WHEN** a LOT has a non-null `PACKAGE_LEF` value
- **THEN** the Package column SHALL display the `package` field value

#### Scenario: Package column with null value
- **WHEN** a LOT has a null or empty `PACKAGE_LEF` value
- **THEN** the Package column SHALL display a dash (`-`)

#### Scenario: Package column is sortable
- **WHEN** user clicks the "Package" column header
- **THEN** the table SHALL sort rows by package value alphabetically (ascending on first click, toggling on subsequent clicks)

#### Scenario: Click bar chart to filter
- **WHEN** user clicks a specific segment of a bar (e.g., QC-GATE-DB's 6-12hr segment)
- **THEN** the table SHALL filter to show only LOTs matching that station AND time bucket
- **THEN** a filter indicator SHALL be visible showing the active filter

#### Scenario: Clear filter
- **WHEN** user clicks the active filter indicator or clicks the same bar segment again
- **THEN** the table SHALL return to showing all QC-GATE LOTs
