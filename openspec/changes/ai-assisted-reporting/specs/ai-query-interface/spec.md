## ADDED Requirements

### Requirement: Function registry for LLM-callable capabilities
The system SHALL maintain an `ai_function_registry.py` module that maps capability names to existing service functions with typed parameter schemas, return descriptions, and drill-down relationships.

#### Scenario: Registry entry structure
- **WHEN** a function is registered in the registry
- **THEN** it SHALL include `description` (Chinese), `service` (dotted path to existing service function), `params` (typed parameter definitions with type/required/enum constraints), `returns` (output description), and `drill_down` (list of follow-up capability names)

#### Scenario: Registry covers all major query domains
- **WHEN** the registry is initialized
- **THEN** it SHALL include entries for at minimum: reject summary, reject reason pareto, reject dimension pareto, reject trend, reject list, hold trend, hold reason pareto, hold duration, hold list, wip summary, wip matrix, equipment status matrix, equipment history summary, lot resolve, filter options, and workcenter groups

#### Scenario: Registry parameters use constrained types
- **WHEN** a parameter has type `enum`
- **THEN** it SHALL define an `options` list of allowed values (e.g., `["reject_total", "defect"]` for metric_mode)

### Requirement: LLM intent parsing service
The system SHALL provide an `ai_query_service.py` that sends user natural language questions to an external LLM API and receives structured intent JSON responses.

#### Scenario: Successful intent parsing
- **WHEN** a user submits a natural language question (e.g., "WB 線最近 7 天不良率最高的原因")
- **THEN** the service SHALL send the question with the function registry system prompt to the LLM and receive a JSON response containing `intent` (function name), `params` (parameter values), and `explanation` (Chinese explanation)

#### Scenario: System prompt contains only capability descriptions
- **WHEN** the system prompt is constructed for the LLM
- **THEN** it SHALL contain only function descriptions, parameter schemas, enum options, drill-down relationships, workcenter group codes, and the current date — it SHALL NOT contain actual manufacturing data, Lot IDs, equipment names, or yield figures

#### Scenario: Unrecognized question
- **WHEN** the LLM cannot map a question to any registered function
- **THEN** it SHALL return `{"intent": null, "explanation": "..."}` and the service SHALL return a user-friendly message suggesting available query types

### Requirement: Intent validation and execution
The system SHALL validate LLM-returned intents against the function registry before executing any query.

#### Scenario: Intent passes validation
- **WHEN** the LLM returns an intent that exists in the function registry and all parameters pass schema validation (type, enum, required fields, date range ≤ 730 days)
- **THEN** the service SHALL dynamically invoke the corresponding service function with the validated parameters

#### Scenario: Intent fails validation — unknown function
- **WHEN** the LLM returns an intent name not present in the function registry
- **THEN** the service SHALL reject the request and return `validation_error("AI 無法識別此查詢類型")`

#### Scenario: Intent fails validation — invalid parameters
- **WHEN** the LLM returns parameters that fail schema validation (e.g., invalid enum value, missing required field, date range > 730 days)
- **THEN** the service SHALL reject the request and return `validation_error("<parameter_name>: <validation_message>")`

#### Scenario: SQL injection prevention
- **WHEN** LLM-returned parameters are passed to service functions
- **THEN** they SHALL flow through the existing `QueryBuilder` bind variable mechanism — no parameter SHALL be interpolated into SQL strings

### Requirement: Result summarizer for token-efficient LLM feedback
The system SHALL provide an `ai_result_summarizer.py` that compresses query results into token-efficient text summaries for optional LLM analysis.

#### Scenario: Pareto result compression
- **WHEN** a Pareto query returns 50 items totaling ~3000 tokens
- **THEN** the summarizer SHALL compress it to a single line (~80 tokens) containing top-5 items with percentages, remaining item count and combined percentage, and total quantity

#### Scenario: Trend result compression
- **WHEN** a trend query returns 30 daily data points
- **THEN** the summarizer SHALL compress it to a single line containing: data point count, mean value, max value with date, min value with date, and recent 7-day mean

#### Scenario: KPI/summary result compression
- **WHEN** a summary/KPI query returns aggregate values
- **THEN** the summarizer SHALL format it as a single line with key metrics (e.g., "投入 10,000, 不良 230, 不良率 2.30%")

#### Scenario: List results are never sent to LLM
- **WHEN** a list/detail query returns paginated lot records
- **THEN** the summarizer SHALL return only "共 N 筆，顯示第 M 頁" — individual lot data SHALL NOT be included

### Requirement: Three-level token strategy
The system SHALL support three token usage levels, with Level 0 as the default.

#### Scenario: Level 0 — intent parsing only (default)
- **WHEN** a user submits a query without requesting analysis
- **THEN** the system SHALL send only the system prompt + question to the LLM (~3K tokens), execute the query locally, and return results for frontend rendering without sending results back to the LLM

#### Scenario: Level 1 — compressed summary feedback
- **WHEN** a user explicitly asks for analysis (e.g., "幫我分析" or "為什麼")
- **THEN** the system SHALL use `ai_result_summarizer` to compress results, send the summary to the LLM for analysis (~5K tokens total), and return the LLM's analysis text alongside the query results

#### Scenario: Token budget enforcement
- **WHEN** a compressed summary would exceed 500 tokens
- **THEN** the system SHALL truncate to top-3 items and add "...及其他 N 項"

### Requirement: AI query API endpoint
The system SHALL expose `POST /api/ai/query` using `success_response()` helpers, registered in `contract/api_inventory.md` as `standard-json`.

#### Scenario: Successful query
- **WHEN** `POST /api/ai/query` is called with `{"question": "...", "context": [...]}`
- **THEN** the system SHALL return `success_response(data)` with `data` containing `answer` (explanation text), `chart_data` (query result), `query_used` (intent name), `params_used` (parameter values), and `suggestions` (drill-down prompts)

#### Scenario: Rate limiting
- **WHEN** a user exceeds 3 requests per minute
- **THEN** the system SHALL return a 429 response with error code `RATE_LIMIT_EXCEEDED`

#### Scenario: LLM API timeout
- **WHEN** the LLM API does not respond within 10 seconds
- **THEN** the system SHALL return `error_response("AI 助手回應逾時", code=EXTERNAL_SERVICE_TIMEOUT, status=504)`

#### Scenario: LLM API unavailable
- **WHEN** the LLM API returns a 5xx error or connection failure
- **THEN** the system SHALL return `error_response("AI 助手暫時不可用", code=EXTERNAL_SERVICE_ERROR, status=502)` and the frontend SHALL display a degradation notice without affecting other dashboard functionality

#### Scenario: Feature flag gating
- **WHEN** the feature flag `AI_QUERY_ENABLED` is `false`
- **THEN** the endpoint SHALL return `not_found_error("Feature not enabled")`

### Requirement: Error code expansion for AI features
The system SHALL extend `core/response.py` with new predefined error code constants for AI-specific failure modes.

#### Scenario: New error codes registered
- **WHEN** the AI query feature is deployed
- **THEN** `core/response.py` SHALL define the following constants: `RATE_LIMIT_EXCEEDED`, `EXTERNAL_SERVICE_TIMEOUT`, `EXTERNAL_SERVICE_ERROR`

### Requirement: AI route layer follows thin-route contract
The AI query API route SHALL be defined in `src/mes_dashboard/routes/ai_routes.py` as a Flask Blueprint. The route SHALL only perform request parsing, rate limiting, service invocation, and response formatting — no business logic.

#### Scenario: Route delegates to service
- **WHEN** `POST /api/ai/query` is called
- **THEN** `ai_routes.py` SHALL parse the JSON body (`question`, `context`), apply `configured_rate_limit()`, call `ai_query_service.process_query(question, context)`, and return the result via `success_response(data)`

#### Scenario: Route registered in API inventory
- **WHEN** the AI route is deployed
- **THEN** `contract/api_inventory.md` SHALL contain an entry for `POST /api/ai/query` under `standard-json` classification, associated with `ai_routes.py`

### Requirement: Multi-turn conversation context
The system SHALL support multi-turn conversations by accepting previous query context in requests.

#### Scenario: Follow-up question with context
- **WHEN** a user submits a question with `context` containing previous rounds' `intent`, `params`, and `summary` (max 3 rounds)
- **THEN** the LLM SHALL receive this context to resolve references like "那個 Reason A 的 Lot 有哪些？"

#### Scenario: Context token budget
- **WHEN** conversation context is included
- **THEN** each round's context SHALL be limited to `intent` + `params` + compressed summary (~100-200 tokens per round), keeping total context under 600 tokens

### Requirement: Backend proxy for LLM API
The system SHALL proxy all LLM API requests through the Flask backend. The frontend SHALL NOT call LLM APIs directly.

#### Scenario: API key stored server-side
- **WHEN** the LLM API is invoked
- **THEN** the API key SHALL be read from server-side environment variables — it SHALL NOT be exposed to the frontend

#### Scenario: No CSP changes required
- **WHEN** the AI query feature is enabled
- **THEN** no changes to the Content-Security-Policy `connect-src` directive SHALL be required

### Requirement: Dual-model strategy
The system SHALL use Claude Haiku for intent parsing and Claude Sonnet for summary analysis to optimize cost and quality.

#### Scenario: Intent parsing uses Haiku
- **WHEN** a Level 0 query is processed (intent parsing only)
- **THEN** the system SHALL call the Haiku model

#### Scenario: Summary analysis uses Sonnet
- **WHEN** a Level 1 query is processed (compressed summary analysis)
- **THEN** the system SHALL call the Sonnet model

#### Scenario: Model selection is configurable
- **WHEN** the system is configured via environment variables
- **THEN** the intent parsing model and summary analysis model SHALL be independently configurable
