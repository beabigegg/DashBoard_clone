## ADDED Requirements

### Requirement: Material Trace page SHALL provide bidirectional query mode switching
The page SHALL provide two query directions with explicit tab switching.

#### Scenario: Forward query mode (default)
- **WHEN** the page loads
- **THEN** "正向查詢：LOT/工單 → 原物料" tab SHALL be active by default
- **THEN** the input area SHALL show input type selector (LOT ID / 工單) and a multi-line text input

#### Scenario: Reverse query mode
- **WHEN** user clicks "反向查詢：原物料 → LOT" tab
- **THEN** the input area SHALL switch to material lot name multi-line input
- **THEN** query results and pagination SHALL be cleared

#### Scenario: Forward input type switching
- **WHEN** forward mode is active
- **THEN** user SHALL be able to switch between "LOT ID" and "工單" input types
- **THEN** switching input type SHALL clear the input field and results

### Requirement: Material Trace page SHALL accept multi-line input
The page SHALL accept multiple values separated by newlines or commas.

#### Scenario: Multi-line input parsing
- **WHEN** user enters values separated by newlines, commas, or mixed delimiters
- **THEN** the system SHALL parse and deduplicate values using the same logic as `parseMultiLineInput()`

#### Scenario: Input count display
- **WHEN** user enters values
- **THEN** the input area SHALL display the parsed count (e.g., "已輸入 5 筆")

#### Scenario: Forward input limit feedback
- **WHEN** user enters more than 200 values in forward mode
- **THEN** the page SHALL display an error message "正向查詢上限 200 筆"
- **THEN** the query SHALL NOT be sent

#### Scenario: Reverse input limit feedback
- **WHEN** user enters more than 50 values in reverse mode
- **THEN** the page SHALL display an error message "反向查詢上限 50 筆"
- **THEN** the query SHALL NOT be sent

### Requirement: Material Trace page SHALL provide workcenter group filter
The page SHALL allow filtering results by workcenter group.

#### Scenario: Workcenter group options
- **WHEN** the page loads
- **THEN** workcenter group filter SHALL be populated from `filter_cache.get_workcenter_groups()`
- **THEN** the filter SHALL support multi-select
- **THEN** default SHALL be "全部站點" (no filter)

#### Scenario: Filter applied to query
- **WHEN** user selects workcenter groups and clicks "查詢"
- **THEN** the selected groups SHALL be sent as `workcenter_groups` parameter to the API
- **THEN** results SHALL only contain records from workcenters in the selected groups

### Requirement: Material Trace page SHALL display query results in a paginated table
The page SHALL display results in a sortable, paginated detail table.

#### Scenario: Result table columns
- **WHEN** query results are loaded
- **THEN** the table SHALL display: LOT ID (CONTAINERNAME), 工單 (PJ_WORKORDER), 站群組 (WORKCENTER_GROUP), 站點 (WORKCENTERNAME), 料號 (MATERIALPARTNAME), 物料批號 (MATERIALLOTNAME), 供應商批號 (VENDORLOTNUMBER), 應領量 (QTYREQUIRED), 實際消耗 (QTYCONSUMED), 機台 (EQUIPMENTNAME), 交易日期 (TXNDATE), 主分類 (PRIMARY_CATEGORY), 副分類 (SECONDARY_CATEGORY)

#### Scenario: Pagination controls
- **WHEN** results exceed per-page size
- **THEN** pagination controls SHALL display "上一頁" / "下一頁" buttons and page info in Chinese
- **THEN** default per-page size SHALL be 50

#### Scenario: Empty results
- **WHEN** query returns no matching records
- **THEN** the table area SHALL display "查無資料" message

#### Scenario: Unresolved LOT IDs warning
- **WHEN** the API response contains `meta.unresolved` array
- **THEN** a warning banner SHALL display listing the unresolvable LOT names

#### Scenario: Result truncation warning
- **WHEN** the API response contains `meta.truncated: true`
- **THEN** an amber warning banner SHALL display "查詢結果超過 10,000 筆上限，請縮小查詢範圍"

### Requirement: Material Trace page SHALL support CSV export
The page SHALL allow exporting current query results to CSV.

#### Scenario: Export button
- **WHEN** query results are loaded
- **THEN** an "匯出 CSV" button SHALL be visible
- **WHEN** user clicks "匯出 CSV"
- **THEN** the export request SHALL use the same query parameters as the current query

#### Scenario: Export disabled without results
- **WHEN** no query has been executed or results are empty
- **THEN** the "匯出 CSV" button SHALL be disabled

### Requirement: Material Trace page SHALL provide loading and error states
The page SHALL provide clear feedback during loading and error conditions.

#### Scenario: Loading state
- **WHEN** a query is in progress
- **THEN** a loading indicator SHALL be visible
- **THEN** the query button SHALL be disabled

#### Scenario: API error
- **WHEN** the API returns an error
- **THEN** a red error banner SHALL display the error message

#### Scenario: Error cleared on new query
- **WHEN** user initiates a new query
- **THEN** previous error and warning banners SHALL be cleared

### Requirement: Material Trace page SHALL use Chinese labels
The page SHALL display all UI text in Traditional Chinese consistent with the rest of the application.

#### Scenario: Page title
- **WHEN** the page is rendered
- **THEN** the page title SHALL be "原物料追溯查詢"

#### Scenario: Button labels
- **WHEN** the page is rendered
- **THEN** the query button SHALL display "查詢"
- **THEN** the export button SHALL display "匯出 CSV"
- **THEN** the clear button SHALL display "清除"
