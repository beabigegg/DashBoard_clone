## REMOVED Requirements

### Requirement: Per-page AnomalyBadge integration
**Reason:** Anomaly display is consolidated into the portal-shell header indicator and the dedicated anomaly overview page. Per-page badges are redundant.
**Migration:** Users see anomaly counts in the header at all times; click to reach the anomaly overview page for details.

#### Scenario: AnomalyBadge removed from yield-alert-center
- **WHEN** the yield-alert-center page renders
- **THEN** it SHALL NOT contain `<AnomalyBadge>` or call `GET /api/analytics/yield-anomalies` for badge display

#### Scenario: AnomalyBadge removed from hold-history
- **WHEN** the hold-history page renders
- **THEN** it SHALL NOT contain `<AnomalyBadge>` or call `GET /api/analytics/hold-outliers` for badge display

#### Scenario: AnomalyBadge removed from reject-history
- **WHEN** the reject-history page renders
- **THEN** it SHALL NOT contain `<AnomalyBadge>` or call `GET /api/analytics/reject-spikes` for badge display

#### Scenario: AnomalyBadge removed from resource-history
- **WHEN** the resource-history page renders
- **THEN** it SHALL NOT contain `<AnomalyBadge>` or call `GET /api/analytics/equipment-deviation` for badge display

### Requirement: AnomalyBadge component deleted
**Reason:** No remaining consumers after per-page integrations are removed.
**Migration:** Anomaly display handled by `AnomalyIndicator.vue` (header) and `anomaly-overview/App.vue` (detail page).

#### Scenario: Component file removed
- **WHEN** this change is deployed
- **THEN** `frontend/src/shared-ui/components/AnomalyBadge.vue` SHALL NOT exist in the codebase

## ADDED Requirements

### Requirement: Anomaly overview page registered as SPA route
The system SHALL provide an anomaly overview page at `/anomaly-overview`, registered as a native SPA route in the portal-shell.

#### Scenario: Route contract registered
- **WHEN** the page is deployed
- **THEN** `routeContracts.js` SHALL include `/anomaly-overview` in `IN_SCOPE_REPORT_ROUTES` with a `ROUTE_CONTRACTS` entry (routeId: `anomaly-overview`, renderMode: `native`, title: `異常總覽`, scope: `in-scope`)

#### Scenario: Standalone drilldown route
- **WHEN** the page is accessed
- **THEN** `/anomaly-overview` SHALL be listed in `STANDALONE_DRILLDOWN_ROUTES` in `navigationState.js` (no sidebar entry required)

#### Scenario: Native module registered
- **WHEN** the shell router navigates to `/anomaly-overview`
- **THEN** `nativeModuleRegistry.js` SHALL load `anomaly-overview/App.vue` with `anomaly-overview/style.css`

#### Scenario: Vite build entry
- **WHEN** the frontend is built
- **THEN** `vite.config.js` SHALL include `'anomaly-overview': resolve(__dirname, 'src/anomaly-overview/index.html')` in `rollupOptions.input`

### Requirement: Summary cards display aggregated counts
The page SHALL display 4 summary cards at the top, one per anomaly type.

#### Scenario: Cards show count and severity
- **WHEN** the page loads and receives the summary response
- **THEN** each card SHALL display the type label (良率異常 / 報廢突增 / Hold 離群 / 稼動偏離), the count, and a severity-colored indicator (ok=green, warning=amber, critical=red)

#### Scenario: Card click scrolls to section
- **WHEN** the user clicks a summary card
- **THEN** the page SHALL scroll to the corresponding detail section below

### Requirement: Detail sections with algorithm explanation
Each anomaly type SHALL have an expandable detail section containing an algorithm explanation card and a data table.

#### Scenario: Algorithm explanation card content
- **WHEN** a detail section is rendered
- **THEN** it SHALL display a card with the detection algorithm formula, window parameter, and threshold value in Chinese:
  - yield: `Z-score = (yield - rolling_avg) / rolling_std，window=7天，threshold=|Z|>2.0`
  - reject: `pct_change = (current - baseline) / baseline × 100，window=7天基線，threshold>50%`
  - hold: `95th percentile of hold_hours，超過此門檻的 hold 記錄`
  - equipment: `deviation = baseline_ou - current_ou，window=30天，threshold>15pp`

#### Scenario: Section expand/collapse
- **WHEN** the user clicks a section header
- **THEN** the section SHALL toggle between expanded (showing table) and collapsed states

#### Scenario: Default expand state
- **WHEN** the page loads
- **THEN** sections with count > 0 SHALL be expanded by default; sections with count = 0 SHALL be collapsed

### Requirement: Data tables show anomaly details
Each expanded section SHALL display a table with the full anomaly list from the corresponding detail API.

#### Scenario: Yield anomalies table columns
- **WHEN** the yield section is expanded
- **THEN** the table SHALL display columns: 日期, 產線, 封裝, 良率%, Z-score, 方向

#### Scenario: Reject spikes table columns
- **WHEN** the reject section is expanded
- **THEN** the table SHALL display columns: 日期, 工作站群組, 目前不良率, 基線不良率, 變化%

#### Scenario: Hold outliers table columns
- **WHEN** the hold section is expanded
- **THEN** the table SHALL display columns: Hold 日期, Lot ID, Hold 原因, 工作站, Hold 時數, 門檻

#### Scenario: Equipment deviations table columns
- **WHEN** the equipment section is expanded
- **THEN** the table SHALL display columns: 日期, 設備 ID, 目前 OU%, 基線 OU%, 偏差

### Requirement: Independent loading states per section
Each detail section SHALL fetch data independently with its own loading state.

#### Scenario: Parallel data fetching
- **WHEN** the page mounts
- **THEN** it SHALL call the summary API first for counts, then call all 4 detail APIs (`/api/analytics/yield-anomalies`, `/api/analytics/reject-spikes`, `/api/analytics/hold-outliers`, `/api/analytics/equipment-deviation`) in parallel

#### Scenario: Section loading indicator
- **WHEN** a detail API is still pending
- **THEN** the corresponding section SHALL display a loading spinner
- **WHEN** a detail API fails
- **THEN** the section SHALL display an error message without affecting other sections

### Requirement: Row click navigates to detail page
Clicking a row in any anomaly table SHALL navigate to the corresponding detail page.

#### Scenario: Yield row navigation
- **WHEN** the user clicks a row in the yield anomalies table
- **THEN** the shell SHALL navigate to `/yield-alert-center`

#### Scenario: Reject row navigation
- **WHEN** the user clicks a row in the reject spikes table
- **THEN** the shell SHALL navigate to `/reject-history`

#### Scenario: Hold row navigation
- **WHEN** the user clicks a row in the hold outliers table
- **THEN** the shell SHALL navigate to `/hold-history`

#### Scenario: Equipment row navigation
- **WHEN** the user clicks a row in the equipment deviations table
- **THEN** the shell SHALL navigate to `/resource-history`

### Requirement: Navigation link per section header
Each section header SHALL include a direct link to the corresponding detail page.

#### Scenario: Section header link
- **WHEN** a section header is rendered
- **THEN** it SHALL include a clickable link labeled `前往 <page name> →` that navigates to the corresponding detail page

### Requirement: Page styles scoped under theme class
All page-specific CSS SHALL be scoped under `.theme-anomaly-overview` in `anomaly-overview/style.css`.

#### Scenario: Theme class applied to root element
- **WHEN** the anomaly-overview page renders
- **THEN** the root element SHALL have the class `theme-anomaly-overview`

#### Scenario: Tailwind tokens only
- **WHEN** styles reference colors, spacing, or shadows
- **THEN** they SHALL use Tailwind utility classes or `theme()` references from `tailwind.config.js` — no hard-coded hex values

#### Scenario: CSS inventory updated
- **WHEN** this change is deployed
- **THEN** `contract/css_inventory.md` SHALL include `frontend/src/anomaly-overview/style.css` in the Route-Local Feature Layers table with theme root `theme-anomaly-overview`
