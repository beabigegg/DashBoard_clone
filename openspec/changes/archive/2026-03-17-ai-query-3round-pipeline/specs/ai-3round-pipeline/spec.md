## ADDED Requirements

### Requirement: YAML function registry
The system SHALL maintain an `ai_functions.yaml` file that defines all LLM-callable functions with descriptions, service paths, parameter schemas, chart types, and drill-down relationships.

#### Scenario: YAML loaded at startup
- **WHEN** the application starts
- **THEN** `ai_function_registry.py` SHALL load `ai_functions.yaml` from the same directory, expanding `$ENUM_NAME` references from the `_enums` section

#### Scenario: Registry entry structure
- **WHEN** a function is defined in the YAML
- **THEN** it SHALL include `description` (Chinese), `service` (dotted module path), `chart_type` (pareto|trend|heatmap|kpi|table), `params` (typed parameter definitions), and `drill_down` (list of follow-up function names)

#### Scenario: Enum reference expansion
- **WHEN** a parameter's `enum` value starts with `$`
- **THEN** the loader SHALL replace it with the corresponding list from the `_enums` section

#### Scenario: Invalid YAML causes clear error
- **WHEN** the YAML file has syntax errors or missing required fields
- **THEN** the module SHALL raise a clear error at import time with the file path and error description

### Requirement: Three-round LLM pipeline
The system SHALL process each user question through three sequential internal LLM calls: intent classification, parameter filling, and result summarization.

#### Scenario: Round 1 — Intent classification
- **WHEN** a user submits a question
- **THEN** the system SHALL send a system prompt containing only function names and one-line descriptions (no parameter details), with the user's question as the user message
- **AND** SHALL expect JSON response: `{"function": "<name>", "explanation": "<one-line Chinese>"}`
- **AND** SHALL use `max_tokens=200`

#### Scenario: Round 1 — Null intent
- **WHEN** the LLM returns `{"function": null, "explanation": "..."}`
- **THEN** the system SHALL return the explanation as `answer` with `chart_data: null` and empty suggestions

#### Scenario: Round 2 — Parameter filling
- **WHEN** Round 1 returns a valid function name
- **THEN** the system SHALL send a system prompt containing ONLY the selected function's full parameter schema (types, enums, descriptions, defaults), current date, and workcenter group list, with the user's question as the user message
- **AND** SHALL expect JSON response: `{"params": {<key-value pairs>}}`
- **AND** SHALL use `max_tokens=300`

#### Scenario: Round 2 — Default parameter filling
- **WHEN** Round 2 returns params missing optional fields that have defaults in the YAML
- **THEN** the system SHALL fill in default values before validation

#### Scenario: Service function dispatch
- **WHEN** Round 2 params pass validation
- **THEN** the system SHALL dynamically import and invoke the service function with validated params, then normalize the result via `_normalize_chart_data`

#### Scenario: Round 3 — Result summarization
- **WHEN** the service function returns chart_data successfully
- **THEN** the system SHALL truncate the result via `_summarize_for_llm`, send a system prompt with analysis instructions, and the user message SHALL be `"{question}\n\n## 查詢結果（{function_name}）\n{truncated_result}"`
- **AND** SHALL expect natural language Chinese text (NOT JSON)
- **AND** SHALL use `max_tokens=500`

#### Scenario: Round 3 — Fallback on failure
- **WHEN** the Round 3 LLM call fails (timeout, parse error, any exception)
- **THEN** the system SHALL return `answer = "查詢完成，請參考圖表。"` with chart_data intact — no error propagated to the user

#### Scenario: Each question is independent
- **WHEN** a user submits any question
- **THEN** the three-round pipeline SHALL NOT include any conversation history from previous questions — each question starts fresh

### Requirement: Result truncation for Round 3
The system SHALL provide `_summarize_for_llm(function_name, chart_data, max_chars=4500)` that truncates query results to fit within LLM context.

#### Scenario: Pareto data truncation
- **WHEN** chart_type is `pareto`
- **THEN** the result SHALL be sent in full (typically 10-20 items)

#### Scenario: Trend data truncation
- **WHEN** chart_type is `trend` and data has > 30 points
- **THEN** the result SHALL include first 5 + last 5 points + summary statistics (min, max, avg, total)

#### Scenario: Heatmap data truncation
- **WHEN** chart_type is `heatmap`
- **THEN** the result SHALL include top-10 cells by value + axis labels + grand total

#### Scenario: KPI data
- **WHEN** chart_type is `kpi`
- **THEN** the result SHALL be sent in full

#### Scenario: Table data truncation
- **WHEN** chart_type is `table` and data has > 10 rows
- **THEN** the result SHALL include first 10 rows with max 5 important columns + `"共 N 筆"`

#### Scenario: Fallback truncation
- **WHEN** chart_type is unknown or data doesn't match any pattern
- **THEN** the result SHALL be `json.dumps(data)[:max_chars]` with trailing `"...(截斷)"`

### Requirement: LLM text response variant
The system SHALL provide `_call_llm_text(messages, max_tokens=None) -> str` that returns raw text content without JSON extraction, used for Round 3.

#### Scenario: Text extraction
- **WHEN** `_call_llm_text` is called
- **THEN** it SHALL return `content || reasoning_content` as plain text, without attempting `json.loads` or regex JSON extraction

### Requirement: Round 1 prompt supports 200+ functions
The Round 1 system prompt SHALL use a compact format (function name + one-line description only) that scales to 200+ functions within 16K context.

#### Scenario: Token efficiency
- **WHEN** `build_round1_prompt()` is called with 16 functions
- **THEN** the generated prompt SHALL be under 600 tokens
