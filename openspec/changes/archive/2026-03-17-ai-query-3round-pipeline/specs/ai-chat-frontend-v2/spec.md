## ADDED Requirements

### Requirement: Multi-step loading animation
The AI chat panel SHALL display a stepped progress indicator during query processing.

#### Scenario: Step text rotation
- **WHEN** a question is submitted and awaiting response
- **THEN** the loading indicator SHALL display step text that rotates every 3 seconds through: "正在分析您的問題..." → "正在準備查詢..." → "正在生成報告..."
- **AND** the three-dot bounce animation SHALL continue alongside the text

#### Scenario: Step text cleared on completion
- **WHEN** the API response arrives (success or error)
- **THEN** the step text timer SHALL be cleared and `loadingStepText` reset to empty

### Requirement: Conversation divider between independent queries
The AI chat panel SHALL visually separate each question-answer pair to indicate they are independent.

#### Scenario: Divider between Q&A pairs
- **WHEN** a previous AI response is followed by a new user message in the messages array
- **THEN** a horizontal divider SHALL be rendered between them with centered text "新的查詢"
- **AND** the divider SHALL use `text-text-muted` color and `border-stroke-soft` line color

#### Scenario: No divider for first message
- **WHEN** the first message in the conversation is a user message
- **THEN** no divider SHALL be rendered above it

### Requirement: Clear history replaces new conversation
The panel header SHALL provide a "清除紀錄" button instead of "新對話".

#### Scenario: Clear history button
- **WHEN** the user clicks "清除紀錄"
- **THEN** the frontend `messages` array SHALL be cleared
- **AND** no backend API call SHALL be made (purely client-side)

#### Scenario: Input always enabled
- **WHEN** the panel is open
- **THEN** the input textarea SHALL always be enabled (no context limit or round limit disabling)
- **UNLESS** `isLoading` or `isRateLimited` is true
