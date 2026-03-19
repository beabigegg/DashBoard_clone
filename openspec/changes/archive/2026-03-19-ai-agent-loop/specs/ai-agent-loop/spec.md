## ADDED Requirements

### Requirement: Orchestrated agentic loop processes user questions
The system SHALL process user questions through an orchestrated agentic loop when `AI_MODE=agent`. Each round of the loop is an independent LLM call — the system (Python code) acts as the orchestrator, assembling each round's prompt from the original question plus accumulated tool result summaries.

#### Scenario: Single tool call
- **WHEN** user asks "焊接站今天不良率多少？"
- **THEN** the system SHALL send Round 1 prompt (system + question) to LLM
- **AND** LLM responds with a `<tool_call>` for `reject_summary`
- **AND** the system executes the tool and collects the result summary
- **AND** the system sends Round 2 prompt (system + question + result summary) to LLM
- **AND** LLM responds with the final answer (no tool_call)

#### Scenario: Multiple tool calls across rounds
- **WHEN** user asks "A 站不良率趨勢和前三大不良原因"
- **THEN** the system SHALL execute the agentic loop
- **AND** LLM requests `reject_trend` and `reject_reason_pareto` via `<tool_call>` tags
- **AND** the system executes both tools and feeds result summaries into the next round
- **AND** LLM produces a unified answer referencing both results

#### Scenario: LLM responds without tool call
- **WHEN** user asks a general question that does not require data lookup (e.g., "你好")
- **THEN** LLM SHALL respond with text only (no `<tool_call>` tags)
- **AND** the system returns the text as the final answer in round 1

### Requirement: Each round uses an independent prompt
The system SHALL construct each round's messages as an independent conversation: `[system_prompt, user_message]`. The user_message SHALL contain the original question plus a "已取得的查詢結果" section with summaries from all previously executed tools. The system SHALL NOT accumulate prior LLM responses in the messages array.

#### Scenario: Round 2 prompt includes prior results
- **WHEN** Round 1 produced a result from `reject_summary`
- **THEN** Round 2's user message SHALL contain the original question followed by `## 已取得的查詢結果\n### reject_summary\n{truncated result}`

### Requirement: Maximum round limit enforced
The system SHALL enforce a maximum of 5 rounds per request. If the loop reaches the maximum without a final answer, the system SHALL return a fallback answer summarizing all collected results.

#### Scenario: Loop reaches max rounds
- **WHEN** LLM keeps requesting tool calls for 5 consecutive rounds
- **THEN** the system SHALL terminate the loop after round 5
- **AND** return an answer indicating the max query limit was reached, along with any collected results

### Requirement: Duplicate tool call prevention
The system SHALL track all tool calls (name + arguments) within a single request. If LLM requests the same tool with the same arguments again, the system SHALL skip execution and inform LLM that the result was already obtained.

#### Scenario: LLM calls same tool twice
- **WHEN** LLM requests `reject_summary` with `{"workcenter": "DB"}` in Round 1 and again in Round 3
- **THEN** the system SHALL skip the duplicate call in Round 3
- **AND** include the original result in the prompt instead

### Requirement: Tool call parsing via regex
The system SHALL parse LLM responses for `<tool_call>{"name":"...","arguments":{...}}</tool_call>` patterns using regex. If JSON parsing fails for a tool_call match, the system SHALL skip that tool_call and continue processing remaining matches.

#### Scenario: Malformed tool call JSON
- **WHEN** LLM outputs `<tool_call>{"name": "reject_summary", INVALID}</tool_call>`
- **THEN** the system SHALL skip this tool_call
- **AND** log a warning
- **AND** continue the loop normally

### Requirement: Agent mode activated via AI_MODE environment variable
The system SHALL support `AI_MODE=agent` as a new mode alongside existing `text2sql` and `function` modes. When `AI_MODE=agent`, `process_query()` SHALL delegate to the agentic loop. Existing modes SHALL remain unchanged.

#### Scenario: AI_MODE=agent routes to agent loop
- **WHEN** `AI_MODE=agent` is set
- **AND** a request arrives at `POST /api/ai/query`
- **THEN** `process_query()` SHALL call `process_agent_turn(question)`

#### Scenario: Existing modes unaffected
- **WHEN** `AI_MODE=text2sql` or `AI_MODE=function` is set
- **THEN** `process_query()` SHALL behave identically to current implementation

### Requirement: Response includes tool trace
The system SHALL return a `tool_trace` array in the response, containing one entry per tool execution with: step number, function name, result summary, and error (if any).

#### Scenario: Tool trace populated
- **WHEN** the agentic loop executes `reject_trend` and `reject_reason_pareto`
- **THEN** `tool_trace` SHALL contain 2 entries with step=1 and step=2 respectively
- **AND** each entry includes the function name and a brief summary

### Requirement: Last chart data returned to frontend
The system SHALL track `chart_data` from each tool execution. The response SHALL include the `chart_data` from the last tool call that produced non-null chart data, for frontend chart rendering.

#### Scenario: Multiple tools with chart data
- **WHEN** `reject_trend` returns trend chart data and `reject_reason_pareto` returns pareto chart data
- **THEN** the response `chart_data` SHALL be the pareto data (last executed)
