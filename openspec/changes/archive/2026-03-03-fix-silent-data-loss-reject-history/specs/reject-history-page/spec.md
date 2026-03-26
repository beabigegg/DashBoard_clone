## ADDED Requirements

### Requirement: Reject History page SHALL display partial failure warning banner
The page SHALL display an amber warning banner when the query result contains partial failures, informing users that displayed data may be incomplete.

#### Scenario: Warning banner displayed on partial failure
- **WHEN** the primary query response includes `meta.has_partial_failure: true`
- **THEN** an amber warning banner SHALL be displayed below the error banner position
- **THEN** the warning message SHALL be in Traditional Chinese

#### Scenario: Warning banner shows failed date ranges
- **WHEN** `meta.failed_ranges` contains date range objects
- **THEN** the warning banner SHALL display the specific failed date ranges (e.g., "以下日期區間的資料擷取失敗：2025-01-01 ~ 2025-01-10")

#### Scenario: Warning banner shows generic message without ranges (container mode or missing range data)
- **WHEN** `meta.has_partial_failure` is true but `meta.failed_ranges` is empty or absent (e.g., container-id batch query)
- **THEN** the warning banner SHALL display a generic message with the failed chunk count (e.g., "3 個查詢批次的資料擷取失敗")

#### Scenario: Warning banner cleared on new query
- **WHEN** user initiates a new primary query
- **THEN** the warning banner SHALL be cleared before the new query executes
- **THEN** if the new query also has partial failures, the warning SHALL update with new failure information

#### Scenario: Warning banner coexists with error banner
- **WHEN** both an error message and a partial failure warning exist
- **THEN** the error banner SHALL appear first, followed by the warning banner

#### Scenario: Warning banner visual style
- **WHEN** the warning banner is rendered
- **THEN** it SHALL use amber/orange color scheme (background `#fffbeb`, text `#b45309`)
- **THEN** the style SHALL be consistent with the existing `.resolution-warn` color pattern

### Requirement: Reject History page SHALL validate date range before query submission
The page SHALL validate the date range on the client side before sending the API request, providing immediate feedback for invalid ranges.

#### Scenario: Date range exceeds 730-day limit
- **WHEN** user selects a date range exceeding 730 days and clicks "查詢"
- **THEN** the page SHALL display an error message "查詢範圍不可超過 730 天（約兩年）"
- **THEN** the API request SHALL NOT be sent

#### Scenario: Missing start or end date
- **WHEN** user clicks "查詢" without setting both start_date and end_date (in date_range mode)
- **THEN** the page SHALL display an error message "請先設定開始與結束日期"
- **THEN** the API request SHALL NOT be sent

#### Scenario: End date before start date
- **WHEN** user selects an end_date earlier than start_date
- **THEN** the page SHALL display an error message "結束日期必須大於起始日期"
- **THEN** the API request SHALL NOT be sent

#### Scenario: Valid date range proceeds normally
- **WHEN** user selects a valid date range within 730 days and clicks "查詢"
- **THEN** no validation error SHALL be shown
- **THEN** the API request SHALL proceed normally

#### Scenario: Container mode skips date validation
- **WHEN** query mode is "container" (not "date_range")
- **THEN** date range validation SHALL be skipped
