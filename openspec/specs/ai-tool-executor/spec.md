## ADDED Requirements

### Requirement: Unified tool execution dispatcher
The system SHALL provide an `execute_tool(name, arguments)` function that dispatches to the appropriate handler based on tool name and returns a standardized result dict with keys: `success`, `result_summary`, `chart_data`, `error`.

#### Scenario: YAML registry tool execution
- **WHEN** `execute_tool("reject_summary", {"start_date": "2026-03-01", "end_date": "2026-03-18"})` is called
- **THEN** the system SHALL validate parameters via `validate_intent()`
- **AND** call the service function via `get_service_function("reject_summary")`
- **AND** normalize the result via `normalize_chart_data()`
- **AND** produce a truncated summary via `summarize_for_llm()` (max 1500 chars)
- **AND** return `{"success": True, "result_summary": "...", "chart_data": [...], "error": None}`

#### Scenario: Unknown tool name
- **WHEN** `execute_tool("nonexistent_tool", {})` is called
- **THEN** the system SHALL return `{"success": False, "result_summary": "", "chart_data": None, "error": "未知工具: nonexistent_tool"}`

### Requirement: query_database special tool
The system SHALL handle the `query_database` tool by delegating to the existing `process_query_text2sql()` pipeline internally. The result's `answer` and `chart_data` SHALL be extracted and returned in the standard result format.

#### Scenario: Ad-hoc SQL query via query_database
- **WHEN** `execute_tool("query_database", {"question": "本月設備稼動率"})` is called
- **THEN** the system SHALL call `process_query_text2sql("本月設備稼動率")`
- **AND** return the text2sql answer as `result_summary` and chart_data

### Requirement: search_tools special tool
The system SHALL handle the `search_tools` tool by searching the YAML function registry for tools matching the given keyword. It SHALL return a list of matching tool names with their descriptions.

#### Scenario: Searching for material-related tools
- **WHEN** `execute_tool("search_tools", {"keyword": "物料"})` is called
- **THEN** the system SHALL search REGISTRY entries whose name or description contains "物料"
- **AND** return matching tool names and descriptions as `result_summary`

#### Scenario: No matching tools found
- **WHEN** `execute_tool("search_tools", {"keyword": "xyz不存在"})` is called
- **THEN** `result_summary` SHALL indicate no matching tools were found

### Requirement: Tool execution errors are caught and returned
The system SHALL catch exceptions during tool execution and return them as structured error results rather than raising exceptions to the caller.

#### Scenario: Service function raises an exception
- **WHEN** `get_service_function("reject_summary")` raises a `TypeError` due to invalid params
- **THEN** `execute_tool` SHALL return `{"success": False, "result_summary": "", "chart_data": None, "error": "參數錯誤: ..."}`
- **AND** SHALL NOT raise the exception to the caller

### Requirement: Default parameter filling from YAML schema
The system SHALL fill default parameter values from the YAML function schema before calling the service function, consistent with existing `process_query_function` behavior.

#### Scenario: Missing optional parameter with default
- **WHEN** `execute_tool("reject_trend", {"start_date": "2026-03-01", "end_date": "2026-03-18"})` is called
- **AND** the YAML schema defines `granularity` with default `"day"`
- **THEN** the system SHALL fill `granularity="day"` before calling the service function
