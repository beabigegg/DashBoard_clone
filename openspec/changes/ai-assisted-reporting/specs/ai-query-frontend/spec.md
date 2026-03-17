## ADDED Requirements

### Requirement: AI chat trigger button
The system SHALL provide a floating action button (FAB) that triggers the AI chat panel, positioned at the bottom-right corner of the viewport.

#### Scenario: Trigger visible on all portal pages
- **WHEN** the user is on any page within the portal shell and `AI_QUERY_ENABLED` is `true`
- **THEN** a circular trigger button SHALL be rendered at `position: fixed; right: 24px; bottom: 24px` with `bg-brand-600 text-white shadow-shell` styling and a chat/AI icon

#### Scenario: Trigger hidden when panel is open
- **WHEN** the AI chat panel is open
- **THEN** the trigger button SHALL NOT be rendered

#### Scenario: Trigger hidden when feature flag is off
- **WHEN** the feature flag `AI_QUERY_ENABLED` is `false`
- **THEN** the trigger button SHALL NOT be rendered

#### Scenario: Mobile trigger sizing
- **WHEN** viewport width is ≤ 768px
- **THEN** the trigger button SHALL shrink to 40px diameter (from 48px)

### Requirement: AI chat panel as right-side slide-out drawer
The system SHALL provide a slide-out panel that opens from the right edge of the viewport, overlaying (not pushing) the main content area.

#### Scenario: Panel slide-in animation
- **WHEN** the user clicks the trigger button
- **THEN** the panel SHALL animate from `translateX(100%)` to `translateX(0)` using `--motion-normal (200ms)` with `--motion-ease` easing

#### Scenario: Panel dimensions on desktop
- **WHEN** viewport width is > 768px
- **THEN** the panel SHALL have width `380px`, height `calc(100vh - var(--shell-header-height))`, positioned below the shell header at `top: var(--shell-header-height)`, with `z-index: 1001`

#### Scenario: Panel full-screen on mobile
- **WHEN** viewport width is ≤ 768px
- **THEN** the panel SHALL expand to `100vw` width with a semi-transparent backdrop overlay (matching the sidebar mobile overlay pattern)

#### Scenario: Panel closable via button and Escape key
- **WHEN** the user clicks the close button in the panel header or presses Escape
- **THEN** the panel SHALL animate out via `translateX(100%)` and conversation state SHALL be preserved

#### Scenario: Panel layout structure
- **WHEN** the panel is open
- **THEN** it SHALL contain three zones: (1) header with title "AI 助手", "新對話" button, and close button; (2) scrollable message area for conversation history; (3) fixed-bottom input bar with text input and send button

#### Scenario: Panel background and styling
- **WHEN** the panel is rendered
- **THEN** it SHALL use `bg-surface-card` background, `shadow-panel` shadow, and `border-l border-stroke-soft` left border, following the design system tokens

### Requirement: AI chat message rendering
The system SHALL render each conversation message with appropriate visual treatment based on message role and content type.

#### Scenario: User message rendering
- **WHEN** a user-submitted question is displayed
- **THEN** it SHALL appear right-aligned with `bg-brand-50 text-text-primary rounded-card p-3` styling

#### Scenario: AI response with explanation
- **WHEN** the API returns successfully with `answer` and `query_used`
- **THEN** the message SHALL display: (1) the explanation text, (2) a `StatusBadge` with `tone-neutral` showing the query type label (e.g., "不良原因排行")

#### Scenario: AI response with Pareto chart
- **WHEN** `chart_data` contains items with `pct` and `cumPct` fields (indicating Pareto data)
- **THEN** the message SHALL render an inline ECharts bar+line dual-axis Pareto chart at 200px height using `VChart` with `autoresize: { throttle: 100 }`, following the `ParetoSection.vue` import pattern

#### Scenario: AI response with trend chart
- **WHEN** `chart_data` contains time-series items with date and value fields
- **THEN** the message SHALL render an inline ECharts line chart at 180px height

#### Scenario: AI response with KPI summary
- **WHEN** `chart_data` contains aggregate KPI values (e.g., `MOVEIN_QTY`, `REJECT_TOTAL_QTY`, `reject_rate`)
- **THEN** the message SHALL render KPI cards in a horizontal flex layout using `bg-surface-muted rounded-card p-2` styling

#### Scenario: AI response with matrix data
- **WHEN** `chart_data` contains matrix/heatmap data
- **THEN** the message SHALL render a mini ECharts heatmap at 160px height

#### Scenario: AI response with list/table data
- **WHEN** `chart_data` contains paginated list items
- **THEN** the message SHALL render a compact HTML table with max 10 visible rows, vertical scroll for overflow, using `text-xs` font size for density

#### Scenario: Chart rendering in compact mode
- **WHEN** any chart is rendered inside the chat panel
- **THEN** it SHALL hide the legend, use simplified tooltips (value only), and constrain width to the panel's inner width minus padding

### Requirement: Drill-down suggestions
The system SHALL display actionable drill-down suggestions after each AI response.

#### Scenario: Suggestions rendered as clickable chips
- **WHEN** the API returns a `suggestions` array
- **THEN** each suggestion SHALL be rendered as a chip button below the response using `bg-brand-50 text-brand-700 border border-brand-100 rounded-full px-3 py-1 text-sm cursor-pointer hover:bg-brand-100` styling

#### Scenario: Clicking a suggestion submits a new question
- **WHEN** the user clicks a suggestion chip
- **THEN** the suggestion text SHALL be submitted as a new question with the current conversation context, and the chip SHALL show a brief pressed state

### Requirement: Conversation context management via useAiChat composable
The frontend SHALL maintain conversation state through a `useAiChat` composable that manages messages, context accumulation, API calls, and rate limiting.

#### Scenario: Composable state structure
- **WHEN** `useAiChat()` is initialized
- **THEN** it SHALL expose: `messages` (ref array), `isOpen` (ref boolean), `isLoading` (ref boolean), `isRateLimited` (ref boolean), `context` (computed from last 3 rounds), `submitQuestion` (async function), `submitSuggestion` (function), `resetConversation` (function), `togglePanel` (function)

#### Scenario: Context accumulates across rounds
- **WHEN** a follow-up question is submitted
- **THEN** the request payload SHALL include `context` containing the last 3 rounds' `intent`, `params`, and compressed `summary` (each round ~100-200 tokens)

#### Scenario: Context resets on new conversation
- **WHEN** the user clicks the "新對話" button
- **THEN** `messages` SHALL be cleared, `context` SHALL reset to empty, and the input SHALL receive focus

#### Scenario: State preserved across panel toggle
- **WHEN** the user closes and reopens the chat panel
- **THEN** all conversation messages, context, and scroll position SHALL be preserved

#### Scenario: Race condition prevention
- **WHEN** a new question is submitted while a previous request is in-flight
- **THEN** the composable SHALL abort the previous request via `AbortController` and only apply the latest response (following `useRequestGuard` pattern)

#### Scenario: Rate limit UI lockout
- **WHEN** the API returns 429
- **THEN** `isRateLimited` SHALL be set to `true`, the send button SHALL be disabled, and a 20-second countdown timer SHALL be displayed; after 20 seconds `isRateLimited` resets to `false`

### Requirement: Error and degradation handling
The system SHALL handle AI query failures gracefully without affecting other dashboard functionality.

#### Scenario: Loading state
- **WHEN** a question is submitted and awaiting response
- **THEN** the chat panel SHALL display a typing indicator animation (three animated dots) in the message area

#### Scenario: LLM API timeout
- **WHEN** the API does not respond within 10 seconds
- **THEN** the chat panel SHALL display an error message "AI 助手回應逾時，請稍後重試" with a retry button that re-submits the same question

#### Scenario: Rate limit exceeded
- **WHEN** the API returns 429
- **THEN** the chat panel SHALL display "查詢頻率過高，請稍後再試" with a countdown timer

#### Scenario: General API error
- **WHEN** the API returns any other error
- **THEN** the chat panel SHALL display the error message with a "使用一般查詢" link that navigates to the most relevant dashboard page based on the attempted `query_used`

#### Scenario: Errors do not affect other dashboard functionality
- **WHEN** the AI chat encounters any error
- **THEN** the main content area, sidebar navigation, and all other dashboard pages SHALL continue to function normally

### Requirement: Portal shell integration
The AI chat components SHALL be integrated into the portal shell without affecting existing layout or functionality.

#### Scenario: Shell class reflects panel state
- **WHEN** the AI chat panel is open
- **THEN** the shell root element SHALL have an `ai-panel-open` CSS class (available for optional layout adjustments)

#### Scenario: Sidebar and chat panel coexistence
- **WHEN** both the sidebar and chat panel are open on desktop
- **THEN** they SHALL coexist without overlap — sidebar on left, chat panel on right, main content between them

#### Scenario: Mobile mutual exclusion
- **WHEN** on mobile (≤ 768px) and the chat panel is opened while the sidebar is open
- **THEN** the sidebar SHALL close automatically before the chat panel opens

### Requirement: Anomaly detection badges on existing pages
The system SHALL display anomaly indicator badges on the yield-alert, reject-history, hold-overview, and resource-status pages when anomalies are detected.

#### Scenario: AnomalyBadge component props
- **WHEN** `AnomalyBadge.vue` is instantiated
- **THEN** it SHALL accept props: `count` (Number), `items` (Array of `{ label, value, severity }`), `type` (String: 'yield' | 'reject' | 'hold' | 'equipment'), and `loading` (Boolean)

#### Scenario: Badge appears when anomalies exist
- **WHEN** the anomaly API returns one or more items for the current filter context
- **THEN** the badge SHALL render inline in the page header, showing the anomaly count (e.g., "⚠ 3 項異常")

#### Scenario: Badge severity escalation
- **WHEN** `count` is > 5
- **THEN** the badge SHALL use danger-level colors (`bg-state-danger/10 text-state-danger`) instead of warning-level

#### Scenario: Badge click opens popover
- **WHEN** the user clicks the badge
- **THEN** a popover SHALL appear below the badge showing top-3 anomaly items with severity icon (🔴/🟡), label, and value; plus a "查看全部異常" link at the bottom

#### Scenario: Popover closes on outside click
- **WHEN** the user clicks outside the popover
- **THEN** the popover SHALL close

#### Scenario: Badge hidden when feature flag is off
- **WHEN** the feature flag `ANALYTICS_ANOMALY_DETECTION_ENABLED` is `false`
- **THEN** no anomaly badges SHALL be rendered on any page

#### Scenario: Badge loading state
- **WHEN** the anomaly API call is in progress
- **THEN** the badge SHALL display a subtle pulse animation (not blocking page content)

#### Scenario: Badge API call is non-blocking
- **WHEN** a page loads with anomaly badge integration
- **THEN** the anomaly API call SHALL be initiated in parallel with the page's main data fetches via `Promise.all`, and badge rendering SHALL NOT delay the main page content

#### Scenario: Badge on yield-alert page
- **WHEN** the yield-alert-center page loads
- **THEN** the page SHALL call `GET /api/analytics/yield-anomalies` and pass results to `AnomalyBadge` with `type="yield"`

#### Scenario: Badge on reject-history page
- **WHEN** the reject-history page loads
- **THEN** the page SHALL call `GET /api/analytics/reject-spikes` and pass results to `AnomalyBadge` with `type="reject"`

#### Scenario: Badge on hold-overview page
- **WHEN** the hold-overview page loads
- **THEN** the page SHALL call `GET /api/analytics/hold-outliers` and pass results to `AnomalyBadge` with `type="hold"`

#### Scenario: Badge on resource-status page
- **WHEN** the resource-status page loads
- **THEN** the page SHALL call `GET /api/analytics/equipment-deviation` and pass results to `AnomalyBadge` with `type="equipment"`

### Requirement: Anomaly badge styling follows design system
The anomaly badges and chat panel SHALL use Tailwind utility classes and design system tokens exclusively.

#### Scenario: Badge uses semantic color tokens
- **WHEN** an anomaly badge is rendered
- **THEN** it SHALL use `state.warning` and `state.danger` tokens from `tailwind.config.js` — no hard-coded hex values

#### Scenario: Badge scoped to feature theme
- **WHEN** a badge is added to the yield-alert page
- **THEN** any custom CSS beyond Tailwind utilities SHALL be scoped under the page's theme class (e.g., `.theme-yield-alert-center`)

#### Scenario: Portal shell theme class added
- **WHEN** the AI chat feature is integrated into portal-shell
- **THEN** `portal-shell/App.vue` SHALL add `theme-portal-shell` class to the `.shell` root element to enable CSS scoping per the CSS contract

#### Scenario: Chat panel styles scoped to portal shell
- **WHEN** custom CSS is needed for the chat panel
- **THEN** it SHALL be placed in `frontend/src/portal-shell/ai-chat.css` and scoped under `.theme-portal-shell`

#### Scenario: CSS inventory updated
- **WHEN** new CSS files are created for AI features
- **THEN** `contract/css_inventory.md` SHALL be updated in the same change

#### Scenario: Motion tokens for animations
- **WHEN** slide-in/out or fade animations are applied
- **THEN** they SHALL use `--motion-fast (150ms)`, `--motion-normal (200ms)`, or `--motion-slow (300ms)` with `--motion-ease` — no hard-coded durations

#### Scenario: ECharts HEX colors registered in governance check
- **WHEN** `AiChartRenderer.vue` uses hard-coded HEX color values for ECharts chart options
- **THEN** these colors SHALL be centralized in a single palette object within `AiChartRenderer.vue`, and the file SHALL be registered as an allow-candidate in `frontend/scripts/css-governance-check.js`
