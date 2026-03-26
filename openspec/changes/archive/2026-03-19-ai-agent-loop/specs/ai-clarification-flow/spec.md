## ADDED Requirements

### Requirement: Backend clarification detection
The system SHALL set `needs_clarification=True` in the response when the agentic loop ends without executing any tools and the LLM's response contains a question mark (`？` or `?`). Otherwise `needs_clarification` SHALL default to `False`.

#### Scenario: LLM asks for missing information
- **WHEN** user asks "不良率多少？" (missing date range and workcenter)
- **AND** LLM responds with "請問您想查看哪個站點和時間範圍的不良率？" without any `<tool_call>`
- **THEN** the response SHALL have `needs_clarification=True`
- **AND** `chart_data` SHALL be `null`

#### Scenario: LLM answers directly without tools
- **WHEN** user asks "MES 是什麼？"
- **AND** LLM responds with a direct answer (no question marks, no tool calls)
- **THEN** `needs_clarification` SHALL be `False`

#### Scenario: LLM uses tools then answers with question
- **WHEN** LLM executes at least one tool and the final answer contains a question mark
- **THEN** `needs_clarification` SHALL be `False` (tools were executed, so this is a real answer with a follow-up suggestion, not a clarification request)

### Requirement: Clarification response includes suggestions
When `needs_clarification=True`, the response SHALL include a `suggestions` array with relevant options for the user to choose from. These suggestions SHALL be derived from the context of the question (e.g., available workcenters, common date ranges).

#### Scenario: Suggestions for workcenter clarification
- **WHEN** LLM asks which workcenter to query
- **THEN** `suggestions` SHALL contain clickable options like `["焊接_DB 不良率", "成型站不良率", "全站不良率"]`

### Requirement: Frontend clarification message rendering
The frontend SHALL render messages with `needs_clarification=True` using a distinct visual style (e.g., different background color) to differentiate them from final answers. Existing suggestion buttons SHALL remain functional for clarification messages.

#### Scenario: Clarification displayed in chat panel
- **WHEN** a response with `needs_clarification=True` is received
- **THEN** the chat panel SHALL display the message with the `clarification` role styling
- **AND** suggestion buttons SHALL be rendered below the message
- **AND** clicking a suggestion SHALL submit it as a new independent question

### Requirement: API response schema backward compatibility
The `needs_clarification` field SHALL be added to the `POST /api/ai/query` response data. For existing `text2sql` and `function` modes, this field SHALL always be `False` to maintain backward compatibility.

#### Scenario: text2sql mode response
- **WHEN** `AI_MODE=text2sql` is set
- **THEN** the response SHALL include `needs_clarification: false`
- **AND** all other response fields SHALL remain unchanged
