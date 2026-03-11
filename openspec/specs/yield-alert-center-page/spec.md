## ADDED Requirements

### Requirement: Yield Alert Center page SHALL be an independent analysis surface
The page SHALL be implemented as a new tool entry and SHALL NOT alter existing Reject History page behavior.

#### Scenario: Navigation entry
- **WHEN** query/trace tools navigation is rendered
- **THEN** UI SHALL provide a dedicated entry for Yield Alert Center
- **THEN** opening Yield Alert Center SHALL keep existing Reject History routes and interactions unchanged

#### Scenario: Independent filter state
- **WHEN** user changes filters in Yield Alert Center
- **THEN** filter state SHALL be scoped to Yield Alert Center context only
- **THEN** leaving and returning to Reject History SHALL not inherit Yield Alert Center temporary selections

### Requirement: Yield Alert Center page SHALL provide yield trend and alert list views
The page SHALL present both macro trend visibility and actionable alert rows for process engineers.

#### Scenario: Initial query rendering
- **WHEN** user applies a valid date range and dimension filters
- **THEN** page SHALL render yield trend cards/charts from API aggregate response
- **THEN** page SHALL render alert list with pagination and sorting controls

#### Scenario: Alert row context visibility
- **WHEN** alert list is displayed
- **THEN** each row SHALL show `date_bucket`, `workorder`, `reason_code`, `scrap_qty`, `yield_pct`, and `risk_level`
- **THEN** row selection SHALL reveal relevant context fields used to compute the alert

### Requirement: Yield Alert Center page SHALL support drilldown to Reject History context
The page SHALL provide a deterministic jump path from an alert item to Reject History detail context.

#### Scenario: Drilldown with linkage keys
- **WHEN** user clicks drilldown on an alert row
- **THEN** UI SHALL pass at least `date_bucket`, `workorder`, and normalized `reason_code` as linkage context
- **THEN** target Reject History query SHALL execute with those linkage filters pre-applied

#### Scenario: Drilldown with partial match warning
- **WHEN** linkage service reports partial or weak mapping for selected alert row
- **THEN** page SHALL still allow navigation to Reject History
- **THEN** UI SHALL display a visible warning that detail result may be incomplete

### Requirement: Yield Alert Center page SHALL provide resilient feedback states
The page SHALL clearly communicate loading, empty, and error states without blocking retry.

#### Scenario: Loading state
- **WHEN** API query is running
- **THEN** page SHALL show loading indicators for trend and alert regions
- **THEN** repeated submit actions SHALL be throttled or disabled until current request completes

#### Scenario: Error and retry
- **WHEN** API request fails
- **THEN** page SHALL display an error banner with retry action
- **THEN** retry SHALL re-submit the same active filter context

## MODIFIED Requirements

### Requirement: Yield Alert Center page SHALL display alert candidate table with inline reason detail
The alert candidate table SHALL allow users to expand individual rows to view MES LOT-level reject reason detail inline, without navigating away from the page.

#### Scenario: Alert table columns (modified)
- **WHEN** the alert candidate table is rendered
- **THEN** it SHALL include columns: 日期、工單、原因碼、站別群組、報廢量、良率(%)、風險分數、操作
- **THEN** it SHALL NOT include a「映射狀態」(match_status) column

#### Scenario: 查看原因 button label
- **WHEN** the alert row is collapsed
- **THEN** the action button SHALL display「查看原因」
- **WHEN** the row is in a loading state (API call in flight)
- **THEN** the button SHALL display「載入中...」and be disabled
- **WHEN** the row is expanded
- **THEN** the button SHALL display「收合」

#### Scenario: Expanding a row
- **WHEN** user clicks「查看原因」on an alert row
- **THEN** the page SHALL call `GET /api/yield-alert/reason-detail` with that row's `workorder` and `date_bucket`
- **THEN** a detail sub-row SHALL appear immediately below the alert row containing a table of MES reject records
- **THEN** at most one row SHALL be expanded at any time (clicking another row collapses the previous one)

#### Scenario: Collapsing a row
- **WHEN** user clicks the action button on an already-expanded row
- **THEN** the detail sub-row SHALL collapse and disappear

#### Scenario: Empty reason detail result
- **WHEN** the API returns `items: []`
- **THEN** the expanded sub-row SHALL display a message:「找不到對應的 MES 報廢明細」

#### Scenario: Reason detail table columns
- **WHEN** MES records are present
- **THEN** the sub-table SHALL display: LOT號 (containername)、站別 (workcentername)、報廢原因 (lossreasonname)、原因代碼 (lossreason_code)、報廢量 (reject_total_qty)、備註 (rejectcomment)

## REMOVED Requirements

### Requirement: Alert table SHALL display match_status for each alert row
**Reason**: linkage analyze 步驟從未被觸發，match_status 永遠為 `none`，欄位對使用者無意義且造成誤導。
**Migration**: 移除 `match_status` td/th 及 `match-pill` CSS；移除前端 `linkageWarning`、`drilldownLoadingKey`、`openDrilldown` 邏輯。

### Requirement: Alert row action SHALL navigate to reject-history page
**Reason**: 跳轉至 reject-history 頁面無法直接提供原因明細，且 drilldown-context 依賴的 linkage 映射永遠失敗。
**Migration**: 改為 inline 展開 MES 報廢明細（見上方 MODIFIED Requirement）。
