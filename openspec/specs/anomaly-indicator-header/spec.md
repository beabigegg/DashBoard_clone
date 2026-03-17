## ADDED Requirements

### Requirement: Anomaly indicator displayed in portal-shell header
The portal-shell header SHALL display an `AnomalyIndicator` component inside `.shell-header-right`, positioned before `<HealthStatus />`.

#### Scenario: Indicator placement
- **WHEN** the portal-shell renders
- **THEN** the `.shell-header-right` element SHALL contain `<AnomalyIndicator />` as the first child, followed by `<HealthStatus />` and the admin entry

### Requirement: Indicator polls anomaly summary
The `AnomalyIndicator` component SHALL poll `GET /api/analytics/anomaly-summary` every 30 seconds starting on mount, and clear the interval on unmount.

#### Scenario: Polling cycle
- **WHEN** the component is mounted
- **THEN** it SHALL immediately fetch the summary, then repeat every 30 seconds
- **WHEN** the component is unmounted
- **THEN** the polling interval SHALL be cleared

### Requirement: Visual severity states
The indicator SHALL display a colored dot and optional count badge reflecting the current anomaly severity.

#### Scenario: No anomalies (ok)
- **WHEN** `total_count` is `0`
- **THEN** the indicator SHALL display a green dot with no count badge, or be visually minimal

#### Scenario: Warning state
- **WHEN** `total_count` is between `1` and `10` (inclusive)
- **THEN** the indicator SHALL display an amber dot (using `state.warning` token) and a count badge showing `total_count`

#### Scenario: Critical state
- **WHEN** `total_count` is greater than `10`
- **THEN** the indicator SHALL display a red dot (using `state.danger` token) with a pulse animation and a count badge showing `total_count`

#### Scenario: Pulse animation uses motion tokens
- **WHEN** the critical pulse animation plays
- **THEN** it SHALL reuse the existing `@keyframes pulse` from `portal-shell/style.css` and use `--motion-normal (200ms)` timing

### Requirement: Feature flag hidden state
The indicator SHALL be hidden when the feature is disabled, with no visual flash during initial load.

#### Scenario: Feature flag off (404 response)
- **WHEN** the summary API returns 404
- **THEN** the entire indicator component SHALL be hidden via `v-if`

#### Scenario: Initial load state
- **WHEN** the component mounts and has not yet received a response
- **THEN** the indicator SHALL remain hidden (initial state = hidden) until the first successful response

### Requirement: Click navigates to overview page
Clicking the indicator SHALL navigate to the anomaly overview page.

#### Scenario: Navigation on click
- **WHEN** the user clicks the anomaly indicator
- **THEN** the shell router SHALL navigate to `/anomaly-overview`

### Requirement: Indicator styles use Tailwind tokens
All indicator styles SHALL use Tailwind semantic tokens from `tailwind.config.js`. No hard-coded hex values.

#### Scenario: Color references
- **WHEN** indicator styles reference colors
- **THEN** they SHALL use `theme('colors.state.warning')`, `theme('colors.state.danger')`, or other defined semantic tokens — no inline hex values

#### Scenario: Styles in portal-shell/style.css
- **WHEN** custom CSS is needed for the indicator
- **THEN** it SHALL be added to `frontend/src/portal-shell/style.css` at shell chrome scope (alongside `.health-trigger` styles)
