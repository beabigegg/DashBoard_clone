# ai-text-to-sql-pipeline Specification

## Purpose
TBD - created by archiving change ai-text-to-sql-migration. Update Purpose after archive.
## Requirements
### Requirement: Feature flag controls pipeline mode
The system SHALL support an environment variable `AI_MODE` with values `text2sql` (default) and `function`. When set to `text2sql`, `process_query()` SHALL delegate to `process_query_text2sql()`. When set to `function`, it SHALL delegate to `process_query_function()` (the existing 3-round pipeline, renamed).

#### Scenario: Default mode is text2sql
- **WHEN** `AI_MODE` environment variable is not set
- **THEN** `process_query()` SHALL use the Text-to-SQL pipeline

#### Scenario: Function mode fallback
- **WHEN** `AI_MODE` is set to `function`
- **THEN** `process_query()` SHALL use the existing 3-round Function Call pipeline unchanged

### Requirement: Stage 1 classifies question into domains
The system SHALL send the user's question to the LLM with a system prompt containing MES domain knowledge (ID format rules, station abbreviations, data source selection logic). The LLM SHALL return a JSON object with `domains` (array of domain keys) and `thought` (explanation string).

#### Scenario: Equipment ID recognized
- **WHEN** user asks "GWBK-0247現在生產的產品?"
- **THEN** Stage 1 SHALL return domains containing `wip_realtime` (recognizing GWBK-xxxx as equipment ID format)

#### Scenario: Work order recognized
- **WHEN** user asks "GA26010001生成的流水批有哪些?"
- **THEN** Stage 1 SHALL return domains containing `genealogy` or `lot_history` (recognizing GA prefix as work order format)

#### Scenario: Station abbreviation mapped
- **WHEN** user asks "WB站OU表現最差的機台?"
- **THEN** Stage 1 SHALL return domains containing `equipment` (mapping WB to 焊接_WB)

#### Scenario: No matching domain
- **WHEN** user asks a question that cannot be mapped to any domain
- **THEN** Stage 1 SHALL return an empty `domains` array and the pipeline SHALL return the `thought` as the answer

### Requirement: Stage 2 generates Oracle SELECT SQL
The system SHALL send the user's question to the LLM with a system prompt containing: (1) table schemas for the domains selected in Stage 1, (2) few-shot SQL examples for those domains, and (3) generation rules. The LLM SHALL return a JSON object with `sql` (Oracle SELECT statement), `params` (bind variable key-value pairs), and `explanation` (one-line description).

#### Scenario: Simple single-table query
- **WHEN** domains include `wip_realtime` and user asks about current equipment production
- **THEN** the generated SQL SHALL query `DWH.DW_MES_EQUIPMENTSTATUS_WIP_V` with appropriate WHERE clause and FETCH FIRST N ROWS ONLY

#### Scenario: Date defaults applied
- **WHEN** user does not specify dates for a historical query
- **THEN** the generated SQL SHALL use bind variables `:start_date` and `:end_date` with params defaulting to 7 days ago and today respectively

#### Scenario: LLM cannot generate SQL
- **WHEN** LLM returns `sql: null`
- **THEN** the pipeline SHALL return the `explanation` as the answer with `chart_data: null`

### Requirement: SQL execution with retry on failure
The system SHALL execute the generated SQL via `read_sql_df(sql, params)`. If execution raises an Oracle error, the system SHALL extract the error message, append it to the Stage 2 conversation history, and request the LLM to generate a corrected SQL. The system SHALL retry at most 2 times (3 total attempts).

#### Scenario: First attempt succeeds
- **WHEN** the generated SQL executes successfully
- **THEN** the pipeline SHALL proceed to Stage 3 with the result DataFrame

#### Scenario: First attempt fails, retry succeeds
- **WHEN** the first SQL execution fails with ORA-00904 (invalid identifier)
- **THEN** the system SHALL feed the error back to the LLM and the LLM SHALL generate corrected SQL
- **AND** if the corrected SQL succeeds, the pipeline SHALL proceed to Stage 3

#### Scenario: All retries exhausted
- **WHEN** all 3 SQL execution attempts fail
- **THEN** the pipeline SHALL return an error message to the user containing the last error, with `chart_data: null`

### Requirement: Stage 3 summarizes query results
The system SHALL send the user's original question and truncated query results to the LLM for natural language summarization. The system SHALL reuse the existing `build_round3_prompt()` and truncation logic (`_summarize_for_llm` / `_summarize_dataframe`).

#### Scenario: Non-empty result
- **WHEN** the executed SQL returns rows
- **THEN** Stage 3 SHALL produce a Chinese natural language summary highlighting 2-3 key data points

#### Scenario: Empty result
- **WHEN** the executed SQL returns zero rows
- **THEN** the pipeline SHALL return "查詢完成，無符合條件的資料。" without calling Stage 3

### Requirement: Response format is backward compatible
The `process_query_text2sql()` return value SHALL include all existing fields (`answer`, `chart_data`, `query_used`, `params_used`, `suggestions`) plus new additive fields (`sql_used`, `tool_trace`). The `query_used` field SHALL be set to `"text2sql"`.

#### Scenario: Response shape
- **WHEN** a text2sql query completes successfully
- **THEN** the response SHALL contain `answer` (string), `chart_data` (list of dicts or null), `query_used` ("text2sql"), `params_used` (dict), `sql_used` (string), `suggestions` (empty list), and `tool_trace` (list of step objects)

#### Scenario: tool_trace structure
- **WHEN** a text2sql query completes
- **THEN** each entry in `tool_trace` SHALL have `step` (int), `function` (string), and `summary` (string), optionally `error` (string)

