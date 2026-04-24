## Purpose
Define stable requirements for hold-history-page.
## Requirements
### Requirement: Hold History page SHALL display a filter bar with date range and hold type
The page SHALL provide a filter bar for selecting date range and hold type classification. On query, the page SHALL use a two-phase flow: `POST /query` returns `queryId`; subsequent supplementary interactions SHALL prefer local browser-side computation when available and otherwise use `GET /view`.

#### Scenario: Primary query via POST /query
- **WHEN** user clicks the query button (or page loads with default filters)
- **THEN** the page SHALL call `POST /api/hold-history/query` with `{ start_date, end_date, hold_type }`
- **THEN** the response `queryId` SHALL be stored for subsequent interactions
- **THEN** trend, reason-pareto, duration, and list SHALL all be populated from the single response
- **THEN** if the response also includes local-compute eligibility metadata, the page SHALL evaluate whether to activate DuckDB-WASM mode

#### Scenario: Supplementary filter change uses local compute when active
- **WHEN** user changes hold_type, record_type, reason, duration, or pagination while DuckDB-WASM mode is active
- **THEN** the page SHALL recompute trend, reason-pareto, duration, and list locally from the downloaded Parquet spool
- **THEN** no `GET /api/hold-history/view` request SHALL be made
- **THEN** no new Oracle query SHALL be triggered

#### Scenario: Supplementary filter change falls back to GET /view
- **WHEN** user changes hold_type radio or clicks a reason in the Pareto chart while DuckDB-WASM mode is inactive or unavailable
- **THEN** the page SHALL call `GET /api/hold-history/view?query_id=...&hold_type=...&reason=...`
- **THEN** no new Oracle query SHALL be triggered
- **THEN** trend, reason-pareto, duration, and list SHALL update from the view response

#### Scenario: Pagination uses the active compute path
- **WHEN** user navigates to a different page in the detail list
- **THEN** the page SHALL use local pagination when DuckDB-WASM mode is active
- **THEN** otherwise the page SHALL call `GET /api/hold-history/view?query_id=...&page=...&per_page=...`

#### Scenario: Page navigation preserves scroll position
- **WHEN** user clicks Next or Prev in the detail table pagination
- **THEN** data SHALL reload with the updated page number
- **THEN** page scroll position SHALL NOT reset to the top
- **THEN** the table content SHALL remain visible in the DOM during loading
- **THEN** a loading overlay SHALL appear on the table section to indicate progress
- **THEN** SummaryCards, DailyTrend, ReasonPareto, and DurationChart SHALL NOT be refreshed as part of pagination

#### Scenario: Table overlay during pagination
- **WHEN** pagination is in progress
- **THEN** the table rows SHALL be visible but visually dimmed (opacity reduced)
- **THEN** user interaction with table rows SHALL be disabled during loading
- **THEN** once data loads, the overlay SHALL be removed and new rows SHALL display

#### Scenario: Date range change triggers new primary query
- **WHEN** user changes the date range and clicks query
- **THEN** the page SHALL call `POST /api/hold-history/query` with new dates
- **THEN** a new `queryId` SHALL replace the old one
- **THEN** any previous local-compute state SHALL be discarded before evaluating the new response

#### Scenario: Cache expired or spool expired auto-retry
- **WHEN** the page cannot refresh because `GET /view` returns `{ success: false, error: "cache_expired" }` or local spool activation fails with an expiry response
- **THEN** the page SHALL automatically re-execute `POST /api/hold-history/query` with the last committed filters
- **THEN** the view SHALL refresh with the new data

#### Scenario: Department still uses separate API
- **WHEN** department data needs to load or reload
- **THEN** the page SHALL call `GET /api/hold-history/department` separately

### Requirement: Hold History SummaryCards SHALL expose released vs on-hold averages and maximums

The SummaryCards row SHALL display separate real-average and real-maximum hold-duration cards for released and still-on-hold lots, replacing the single bucket-weighted estimate.

#### Scenario: SummaryCards shows averages and maximums

- **WHEN** the Hold History page renders SummaryCards with a successful dataset
- **THEN** the cards row SHALL include:
  - "已解除平均時長" bound to `summary.avgReleasedHours` (from duration payload, format `duration`, sub `hr`)
  - "持續 Hold 平均時長" bound to `summary.avgOnHoldHours` (from duration payload, format `duration`, sub `hr`)
  - "已解除最長時長" bound to `summary.maxReleasedHours` (from duration payload, format `duration`, sub `hr`)
  - "持續 Hold 最長時長" bound to `summary.maxOnHoldHours` (from duration payload, format `duration`, sub `hr`)
- **AND** the previous single "平均 Hold 時長" card SHALL be removed
- **AND** `SummaryCardGroup` columns count SHALL be adjusted to accommodate all cards while keeping a readable layout on 1920+ screens

#### Scenario: Average and maximum cards handle empty result sets

- **WHEN** any of `avgReleasedHours` / `avgOnHoldHours` / `maxReleasedHours` / `maxOnHoldHours` equals 0 because no rows match
- **THEN** each respective card SHALL render `0` (or a placeholder agreed with UI review) via `format="duration"` without breaking the layout

### Requirement: Hold History frontend SHALL remove bucket-weighted average estimate

The frontend SHALL source hold-duration averages and maximums from the API response, and SHALL NOT locally derive them from bucket midpoints.

#### Scenario: No bucket-midpoint estimation remains

- **WHEN** the Hold History page source is inspected
- **THEN** the `estimateAvgHoldHours()` function SHALL NOT exist in `frontend/src/hold-history/App.vue`
- **AND** the computed `summary` object SHALL source all four average/maximum values from `durationData.value`, not from `durationData.value.items`

#### Scenario: DuckDB-WASM local-compute path produces matching values

- **WHEN** the page runs in client-side DuckDB compute mode (`useHoldHistoryDuckDB.computeView`)
- **THEN** the local `queryDuration()` SHALL also compute all four values (`avgReleasedHours`, `avgOnHoldHours`, `maxReleasedHours`, `maxOnHoldHours`) using the same filter conditions as the bucket query
- **AND** the returned duration object SHALL include all four fields with the same shape as the server response

### Requirement: Hold History SummaryCards SHALL include a quality repeat-hold indicator

A "品質重複觸發" card SHALL display the stable quality re-hold count that is independent of `FUTUREHOLDCOMMENTS` content mutation.

#### Scenario: Quality repeat-hold card is visible

- **WHEN** the Hold History page renders SummaryCards with a successful dataset
- **THEN** the cards row SHALL include a "品質重複觸發" card bound to `summary.repeatQualityHoldQty` (format `number`)
- **AND** the value SHALL be the sum of daily `repeatQualityHoldQty` from the trend payload across the query range
- **AND** the card SHALL be positioned adjacent to "累計 Future Hold" for semantic comparison

#### Scenario: Card provides contextual label

- **WHEN** the user hovers or focuses the "品質重複觸發" card
- **THEN** an inline help text (or aria-label) SHALL explain: "同工單同原因的 quality Hold 再次發生總量（基於歷史重複推斷，不依賴 FutureHold 備註，值不會衰減）"

### Requirement: Hold History Future Hold card SHALL document its time-decay semantics

The existing "累計 Future Hold" card SHALL remain but SHALL expose a tooltip that explains the decay behavior observed when MES clears `FUTUREHOLDCOMMENTS` on release.

#### Scenario: Future Hold card tooltip is available

- **WHEN** the user hovers or focuses the "累計 Future Hold" card
- **THEN** a tooltip (or equivalent accessible affordance) SHALL be shown explaining:
  - The card counts holds where `FUTUREHOLDCOMMENTS IS NOT NULL AND RN_FUTURE_REASON > 1` (matching PJMES043 original logic)
  - Values for historical days may shrink over time because MES can clear `FUTUREHOLDCOMMENTS` after release
  - For a stable re-hold indicator, users should refer to "品質重複觸發"
- **AND** the tooltip content SHALL be sourced from i18n messages for future localization

### Requirement: Hold History page SHALL support a range-mode / today-mode switch

The FilterBar SHALL expose a mode toggle allowing users to switch between "區間查詢" (range mode, existing behavior) and "當日" (today mode, new behavior). The URL SHALL include a `mode` query parameter that persists the active mode across page reloads and shareable URLs.

#### Scenario: Mode toggle in FilterBar

- **WHEN** the Hold History page renders
- **THEN** the FilterBar SHALL include a mode switch (button group, tab, or radio) labeled "區間查詢" and "當日"
- **AND** the current mode SHALL be visually distinguished
- **AND** each option SHALL include a tooltip or description clarifying its data semantics

#### Scenario: URL reflects mode

- **WHEN** the user is in range mode
- **THEN** the URL SHALL contain `mode=range` (or omit the param, treated as default)
- **AND** `start_date` / `end_date` / `hold_type` / `reason` / `duration_range` / `page` SHALL be URL-synced as today

- **WHEN** the user is in today mode
- **THEN** the URL SHALL contain `mode=today`
- **AND** `start_date` / `end_date` SHALL NOT be present (date is server-derived)
- **AND** `record_type` / `hold_type` / `reason` / `duration_range` / `page` SHALL be URL-synced

#### Scenario: Mode switch clears incompatible params

- **WHEN** the user switches from range to today
- **THEN** `start_date` and `end_date` SHALL be removed from URL
- **AND** `record_type` SHALL reset to default `on_hold`

- **WHEN** the user switches from today to range
- **THEN** `record_type` SHALL be removed from URL (range mode does not expose this filter)
- **AND** `start_date` / `end_date` SHALL default to the current month range

#### Scenario: Browser history navigation works

- **WHEN** the user switches modes and then clicks browser back / forward
- **THEN** the page SHALL restore the state corresponding to the URL (including mode)
- **AND** the appropriate API (`/query` for range, `/today-snapshot` for today) SHALL be invoked

### Requirement: Range mode SHALL drop Record Type filter and rename related cards

In range mode the Record Type filter SHALL no longer be rendered, and the "最末日新增 Hold" card SHALL no longer appear (its semantic is now covered by today mode).

#### Scenario: RecordTypeFilter is hidden in range mode

- **WHEN** the page is in range mode
- **THEN** the `RecordTypeFilter` component SHALL NOT be rendered
- **AND** the backend query SHALL be called without a `record_type` parameter (or equivalent default `new`)

#### Scenario: 最末日新增 Hold card is removed

- **WHEN** range-mode SummaryCards renders
- **THEN** the "最末日新增 Hold" card SHALL NOT be present
- **AND** the card count SHALL be updated accordingly

### Requirement: Today mode SHALL show an "as-of-now + today-events" dashboard

In today mode, the page SHALL display a distinct SummaryCards set focused on current state + today-local events, a hidden Daily Trend, and Pareto / Duration linked to a re-purposed Record Type filter.

#### Scenario: SummaryCards composition in today mode

- **WHEN** the page is in today mode
- **THEN** SummaryCards SHALL include:
  - "On Hold 總量 (件數)" bound to `summary.onHoldTotalCount`
  - "On Hold 總量 (QTY)" bound to `summary.onHoldTotalQty`
  - "今日新增" bound to `summary.todayNewQty`
  - "今日 Release" bound to `summary.todayReleaseQty`
  - "今日 Future Hold" bound to `summary.todayFutureHoldQty`
  - "On Hold 平均時長" bound to `summary.onHoldAvgHours`
  - "On Hold 最長時長" bound to `summary.onHoldMaxHours`
- **AND** each card SHALL include a tooltip / sub-label clarifying the data semantics (e.g., "不限 hold_day，當下仍在 hold 的所有 lot")

#### Scenario: Daily Trend is hidden in today mode

- **WHEN** the page is in today mode
- **THEN** the `DailyTrend` component SHALL NOT be rendered
- **AND** the layout SHALL reflow to use the freed vertical space gracefully

#### Scenario: Record Type filter in today mode uses new semantics

- **WHEN** the page is in today mode and Record Type is `on_hold`
- **THEN** Pareto / Duration / Detail SHALL be derived from all lots with `RELEASETXNDATE IS NULL` (any hold_day)

- **WHEN** Record Type is `new` in today mode
- **THEN** Pareto / Duration / Detail SHALL be derived from lots with `hold_day = today`

- **WHEN** Record Type is `release` in today mode
- **THEN** Pareto / Duration / Detail SHALL be derived from lots with `release_day = today`

- **WHEN** the Record Type filter is displayed in today mode
- **THEN** the UI label SHALL clearly describe the new semantics (e.g., "現況 on hold" instead of just "on_hold")

### Requirement: Today mode SHALL auto-refresh while page is visible

The today-mode page SHALL automatically re-fetch the snapshot every `HOLD_TODAY_AUTO_REFRESH_SECONDS` (default 60) while the page is visible, and pause when the page is hidden or unmounted.

#### Scenario: Timer starts on mount in today mode

- **WHEN** the page enters today mode (initial load or mode switch)
- **THEN** a timer SHALL schedule repeated calls to `POST /api/hold-history/today-snapshot`
- **AND** the interval SHALL be the configured refresh seconds

#### Scenario: Timer pauses on tab hidden

- **WHEN** the page becomes hidden (`document.visibilityState === 'hidden'`)
- **THEN** the timer SHALL pause and no new API calls SHALL be issued

- **WHEN** the page becomes visible again
- **THEN** the timer SHALL resume immediately (fire once to refresh, then resume interval)

#### Scenario: Timer clears on unmount or mode switch

- **WHEN** the user switches to range mode or navigates away
- **THEN** any scheduled timer SHALL be cleared
- **AND** pending in-flight requests SHALL be aborted if practical

#### Scenario: Last-known snapshot retained on failure

- **WHEN** an auto-refresh call fails (network, 5xx, circuit-open)
- **THEN** the previously rendered snapshot SHALL remain visible
- **AND** a non-blocking stale-data indicator SHALL appear, noting the time since last successful refresh

### Requirement: Detail table SHALL support drag-to-resize column widths

The DetailTable SHALL allow users to drag column boundaries to resize columns. Widths are kept while paginating within the current page visit, and reset upon navigating away or reloading.

#### Scenario: Column resize via pointer drag

- **WHEN** the user presses and drags a column boundary (resize handle)
- **THEN** the column width SHALL update in real time
- **AND** neighboring columns SHALL reflow to keep the table layout stable

#### Scenario: Widths persist across pagination within the session

- **WHEN** the user resizes columns and then clicks next / prev page
- **THEN** the new widths SHALL be preserved

#### Scenario: Widths reset on navigation away

- **WHEN** the user navigates to another page or reloads the browser
- **THEN** column widths SHALL reset to defaults on next mount

#### Scenario: Graceful fallback on non-pointer devices

- **WHEN** the user agent does not support pointer events
- **THEN** columns SHALL render at default widths without resize handles and SHALL NOT throw errors

### Requirement: All filter and card labels SHALL clearly communicate the active data scope

Each interactive element (mode toggle, Record Type, Pareto / Duration / Detail headings, summary cards) SHALL include a label, sub-label, or tooltip stating precisely what filter conditions produce the displayed data.

#### Scenario: Contextual labels always visible

- **WHEN** any data panel renders
- **THEN** a label SHALL state: the active mode (range / today), the active Record Type (if applicable), the active Reason (if applicable), and the active Duration Range (if applicable)
- **AND** when no filter is active, the label SHALL read the equivalent of "全部" or the mode-specific default (e.g., "今日全部")

#### Scenario: Tooltip disambiguates same-name cards across modes

- **WHEN** a card name appears in both modes but with different semantics (e.g., "Future Hold")
- **THEN** the tooltip SHALL explicitly state the mode-specific calculation rule

