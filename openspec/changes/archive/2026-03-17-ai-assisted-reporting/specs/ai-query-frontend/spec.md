## ADDED Requirements

### Requirement: AI chat trigger button
The system SHALL provide a floating action button (FAB) that triggers the AI chat panel, positioned at the bottom-right corner of the viewport.

#### Scenario: Trigger visible on all portal pages
- **WHEN** the user is on any page within the portal shell and `AI_QUERY_ENABLED` is `true`
- **THEN** a circular trigger button SHALL be rendered at `position: fixed; right: 24px; bottom: 24px` with `bg-brand-600 text-white shadow-shell` styling and an AI icon (inline SVG)

#### Scenario: Trigger hidden when panel is open
- **WHEN** the AI chat panel is open
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
- **THEN** it SHALL contain three zones:
  1. **Header**: title "AI 助手", round counter "N/5", "新對話" button, and close button
  2. **Scrollable message area**: conversation history with auto-scroll to bottom on new messages
  3. **Fixed-bottom input bar**: textarea (Enter to send, Shift+Enter for newline), send button, status indicators

#### Scenario: Panel background and styling
- **WHEN** the panel is rendered
- **THEN** it SHALL use `bg-surface-card` background, `shadow-panel` shadow, and `border-l border-stroke-soft` left border, following the design system tokens

### Requirement: Conversation round tracking and context limit UX
The system SHALL display conversation progress and handle context limits gracefully.

#### Scenario: Round counter display
- **WHEN** a conversation is active (conversationId is not null)
- **THEN** the panel header SHALL display the current round as "N/5" (e.g., "2/5") next to the title

#### Scenario: Round counter hidden for new conversation
- **WHEN** no conversation is active (conversationId is null)
- **THEN** the round counter SHALL NOT be displayed

#### Scenario: Input disabled at round limit
- **WHEN** `currentRound >= maxRounds` (default 5)
- **THEN** the input textarea SHALL be disabled, the send button SHALL be disabled, and a notice SHALL appear above the input bar: "對話已達上限，請點擊「新對話」繼續"

#### Scenario: Input disabled on context limit error
- **WHEN** the API returns error code `CONTEXT_LIMIT_REACHED`
- **THEN** `isContextFull` SHALL be set to `true`, the input SHALL be disabled, and the same notice SHALL appear: "對話已達上限，請開啟新對話"

#### Scenario: New conversation resets all state
- **WHEN** the user clicks the "新對話" button
- **THEN** `messages` SHALL be cleared, `conversationId` SHALL be reset to null, `currentRound` SHALL reset to 0, `isContextFull` SHALL reset to false, and the input textarea SHALL receive focus

#### Scenario: Single-turn notice for users
- **WHEN** the chat panel is first opened with no active conversation
- **THEN** a welcome message SHALL be displayed explaining: "歡迎使用 AI 助手！您可以用自然語言查詢生產數據。每次對話最多 5 輪問答。" followed by example questions as clickable chips

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
- **THEN** the suggestion text SHALL be submitted as a new question with the current `conversation_id`, and the chip SHALL show a brief pressed state

#### Scenario: Suggestions disabled when context is full
- **WHEN** `isContextFull` is `true` or `currentRound >= maxRounds`
- **THEN** suggestion chips SHALL be visually dimmed and non-clickable

### Requirement: Conversation state management via useAiChat composable
The frontend SHALL maintain conversation state through a `useAiChat` composable that manages messages, conversation tracking, API calls, and rate limiting.

#### Scenario: Composable state structure
- **WHEN** `useAiChat()` is initialized
- **THEN** it SHALL expose: `messages` (ref array), `conversationId` (ref string|null), `currentRound` (ref number), `maxRounds` (ref number, default 5), `isOpen` (ref boolean), `isLoading` (ref boolean), `isRateLimited` (ref boolean), `isContextFull` (ref boolean), `submitQuestion` (async function), `submitSuggestion` (function), `resetConversation` (function), `togglePanel` (function), `canSubmit` (computed boolean)

#### Scenario: Submit question sends conversation_id
- **WHEN** `submitQuestion(question)` is called
- **THEN** the request payload SHALL be `{ question, conversation_id: conversationId.value }` (conversation_id is null for first question)
- **AND** on success, `conversationId`, `currentRound`, and `maxRounds` SHALL be updated from the response

#### Scenario: State preserved across panel toggle
- **WHEN** the user closes and reopens the chat panel
- **THEN** all conversation messages, conversationId, currentRound, and scroll position SHALL be preserved

#### Scenario: Race condition prevention
- **WHEN** a new question is submitted while a previous request is in-flight
- **THEN** the composable SHALL abort the previous request via `AbortController` and only apply the latest response (following `useRequestGuard` pattern)

#### Scenario: Rate limit UI lockout
- **WHEN** the API returns 429
- **THEN** `isRateLimited` SHALL be set to `true`, the send button SHALL be disabled, and a 20-second countdown timer SHALL be displayed; after 20 seconds `isRateLimited` resets to `false`

#### Scenario: canSubmit computed
- **WHEN** any state changes
- **THEN** `canSubmit` SHALL be `true` only when `!isLoading && !isRateLimited && !isContextFull && currentRound < maxRounds`

### Requirement: Error and degradation handling
The system SHALL handle AI query failures gracefully without affecting other dashboard functionality.

#### Scenario: Loading state
- **WHEN** a question is submitted and awaiting response
- **THEN** the chat panel SHALL display a typing indicator animation (three animated dots) in the message area

#### Scenario: LLM API timeout
- **WHEN** the API returns `EXTERNAL_SERVICE_TIMEOUT`
- **THEN** the chat panel SHALL display an error message "AI 助手回應逾時，請稍後重試" with a retry button that re-submits the same question

#### Scenario: Context limit reached
- **WHEN** the API returns `CONTEXT_LIMIT_REACHED`
- **THEN** the chat panel SHALL display "對話已達上限，請點擊「新對話」繼續" and set `isContextFull = true` (disabling further input)

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

#### Scenario: Theme class added for CSS scoping
- **WHEN** the AI chat feature is integrated
- **THEN** `portal-shell/App.vue` SHALL add `theme-portal-shell` class to the `.shell` root element

#### Scenario: Sidebar and chat panel coexistence
- **WHEN** both the sidebar and chat panel are open on desktop
- **THEN** they SHALL coexist without overlap — sidebar on left, chat panel on right, main content between them

#### Scenario: Mobile mutual exclusion
- **WHEN** on mobile (≤ 768px) and the chat panel is opened while the sidebar is open
- **THEN** the sidebar SHALL close automatically before the chat panel opens

### Requirement: AI chat styling follows design system
The AI chat panel and related components SHALL use Tailwind utility classes and design system tokens exclusively.

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
