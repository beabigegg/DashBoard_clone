## ADDED Requirements

### Requirement: Frontend parses new response fields
The `useAiChat.js` composable SHALL parse `sql_used` (string or null) and `tool_trace` (array) from the API response and attach them to the AI message object.

#### Scenario: Text-to-SQL response
- **WHEN** the API response contains `sql_used` and `tool_trace`
- **THEN** the message object SHALL include `sqlUsed` and `toolTrace` properties

#### Scenario: Function mode response (no new fields)
- **WHEN** the API response does not contain `sql_used`
- **THEN** `sqlUsed` SHALL be `null` and `toolTrace` SHALL be an empty array

### Requirement: Collapsible SQL display in chat message
The `AiChatMessage.vue` component SHALL render a collapsible `<details>` element showing the generated SQL when `message.sqlUsed` is present.

#### Scenario: SQL is shown
- **WHEN** a message has `sqlUsed` with a non-null value
- **THEN** a collapsed `<details>` with summary "查看 SQL" SHALL be rendered
- **AND** expanding it SHALL show the SQL in a `<pre>` block with monospace font and horizontal scroll

#### Scenario: No SQL available
- **WHEN** a message has `sqlUsed` as null (e.g., function mode)
- **THEN** no SQL details element SHALL be rendered

### Requirement: Execution trace display for multi-step queries
The `AiChatMessage.vue` component SHALL render a collapsible execution trace when `message.toolTrace` contains more than 1 step.

#### Scenario: Multi-step trace shown
- **WHEN** `toolTrace` has 2 or more entries
- **THEN** a collapsed `<details>` with summary "查詢步驟 (N 步)" SHALL be rendered
- **AND** each step SHALL display function name and summary

#### Scenario: Single-step query hides trace
- **WHEN** `toolTrace` has 0 or 1 entries
- **THEN** no trace details element SHALL be rendered (UI identical to current behavior)
