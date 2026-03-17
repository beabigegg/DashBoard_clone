## REMOVED Requirements

### Requirement: Conversation round tracking and context limit UX
**REMOVED** — Each question is independent; no round tracking or context limits.

Removed state:
- `conversationId` ref
- `currentRound` ref
- `maxRounds` ref
- `isContextFull` ref
- `canSubmit` context/round checks (simplified to `!isLoading && !isRateLimited`)

Removed UI elements:
- Header round counter "N/5"
- Input disabled at round limit notice
- Input disabled on `CONTEXT_LIMIT_REACHED` notice
- "新對話" button (replaced by "清除紀錄")

Removed logic:
- `CONTEXT_LIMIT_REACHED` error handling in `useAiChat.js`
- `conversation_id` in request body
- `conversation_id`, `current_round`, `max_rounds` from response parsing
- `resetConversation()` (replaced by `clearHistory()`)

### Requirement: Suggestion chips disabled when context full
**REMOVED** — `isContextFull` no longer exists; suggestion chips are always clickable when not loading.

## CHANGED Requirements

### Requirement: useAiChat composable state
**CHANGED** — Simplified state structure.

#### Scenario: Composable state
- **WHEN** `useAiChat()` is initialized
- **THEN** it SHALL expose: `messages` (ref array), `isOpen` (ref boolean), `isLoading` (ref boolean), `isRateLimited` (ref boolean), `loadingStepText` (ref string), `submitQuestion` (async function), `submitSuggestion` (function), `clearHistory` (function), `togglePanel` (function), `canSubmit` (computed: `!isLoading && !isRateLimited`)

#### Scenario: Submit question payload
- **WHEN** `submitQuestion(question)` is called
- **THEN** the request payload SHALL be `{ question }` only — no `conversation_id`

### Requirement: AI chat panel layout
**CHANGED** — Header simplified.

#### Scenario: Panel header
- **WHEN** the panel is open
- **THEN** the header SHALL contain: title "AI 助手", "清除紀錄" button, and close button — no round counter
