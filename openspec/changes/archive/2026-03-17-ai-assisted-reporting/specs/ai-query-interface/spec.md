## ADDED Requirements

### Requirement: Function registry for LLM-callable capabilities
The system SHALL maintain an `ai_function_registry.py` module that maps capability names to existing service functions with typed parameter schemas, return descriptions, and drill-down relationships.

#### Scenario: Registry entry structure
- **WHEN** a function is registered in the registry
- **THEN** it SHALL include `description` (Chinese), `service` (dotted path to existing service function), `params` (typed parameter definitions with type/required/enum constraints), `returns` (output description), and `drill_down` (list of follow-up capability names)

#### Scenario: Registry covers all major query domains
- **WHEN** the registry is initialized
- **THEN** it SHALL include entries for at minimum: reject reason pareto, reject trend, reject spike alerts, yield anomaly alerts, yield alert detail, wip summary, wip matrix, wip hold summary, hold outlier alerts, hold history trend, hold reason pareto, equipment deviation alerts, equipment status summary, lot query, and equipment recent jobs (~15 functions)

#### Scenario: Registry parameters use constrained types
- **WHEN** a parameter has type `enum`
- **THEN** it SHALL define an `options` list of allowed values

#### Scenario: System prompt generation
- **WHEN** `build_system_prompt()` is called
- **THEN** it SHALL dynamically generate a system prompt from the REGISTRY containing: response format instructions (strict JSON only), function descriptions with parameter schemas, workcenter group code list, parameter explanations, and rules (whitelist-only, normalize to uppercase codes)
- **AND** the generated prompt SHALL be approximately 676 tokens (measured against gpt-oss:120b tokenizer)

### Requirement: LLM intent parsing service
The system SHALL provide an `ai_query_service.py` that sends user natural language questions to an internal LLM API and receives structured intent JSON responses.

#### Scenario: Successful intent parsing
- **WHEN** a user submits a natural language question (e.g., "WB 線最近 7 天不良率最高的原因")
- **THEN** the service SHALL send the question with the function registry system prompt to the LLM and receive a JSON response containing `function` (function name), `params` (parameter values), and `explanation` (Chinese explanation)

#### Scenario: System prompt contains only capability descriptions
- **WHEN** the system prompt is constructed for the LLM
- **THEN** it SHALL contain only function descriptions, parameter schemas, enum options, drill-down relationships, workcenter group codes, and the current date — it SHALL NOT contain actual manufacturing data, Lot IDs, equipment names, or yield figures

#### Scenario: Unrecognized question
- **WHEN** the LLM cannot map a question to any registered function
- **THEN** it SHALL return `{"function": null, "explanation": "..."}` and the service SHALL return a user-friendly message suggesting available query types

#### Scenario: LLM response parsing — dual content path
- **WHEN** the LLM returns a response
- **THEN** the service SHALL read `choices[0].message.content` first; if empty, fall back to `choices[0].message.reasoning_content`
- **AND** SHALL extract JSON from the response text using `json.loads()` first, falling back to regex extraction `re.search(r'\{.*\}', text, re.DOTALL)` if direct parsing fails

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

### Requirement: Multi-turn conversation management via Redis
The system SHALL support up to 5 rounds of multi-turn conversation per session, with conversation state stored in Redis.

#### Scenario: New conversation creation
- **WHEN** a user submits a question without a `conversation_id`
- **THEN** the service SHALL generate a new UUID as `conversation_id`, create a Redis key `ai_chat:{user_id}:{conversation_id}` with the initial messages array and `round_count: 1`, set TTL to `AI_CONVERSATION_TTL` (default 1800 seconds), and return the `conversation_id` in the response

#### Scenario: Continuing an existing conversation
- **WHEN** a user submits a question with a valid `conversation_id`
- **THEN** the service SHALL read the conversation from Redis, verify the `user_id` matches the key's owner, append the new user message to the history, increment `round_count`, call the LLM with the full messages array `[system, ...history, new_user]`, append the assistant response, save back to Redis with TTL refresh, and return updated `round`, `max_rounds`, and `conversation_id`

#### Scenario: Conversation ownership validation
- **WHEN** a user submits a `conversation_id` that belongs to a different user
- **THEN** the service SHALL reject the request (treat as conversation not found, create new conversation)

#### Scenario: Round limit exceeded
- **WHEN** `round_count` exceeds `AI_MAX_ROUNDS` (default 5)
- **THEN** the service SHALL return an error with code `CONTEXT_LIMIT_REACHED` and message "對話已達上限，請開啟新對話"

#### Scenario: Context token limit exceeded
- **WHEN** the estimated prompt tokens (system + all history + new message) exceed `AI_CONTEXT_TOKEN_LIMIT` (default 12,000)
- **THEN** the service SHALL return an error with code `CONTEXT_LIMIT_REACHED` and message "對話上下文已達上限，請開啟新對話"

#### Scenario: Token estimation
- **WHEN** the service needs to estimate prompt tokens before calling the LLM
- **THEN** it SHALL use a simple heuristic: Chinese characters ≈ 1.5 chars/token, ASCII characters ≈ 4 chars/token, applied to the concatenated content of all messages

#### Scenario: Conversation TTL and cleanup
- **WHEN** a conversation is idle for longer than `AI_CONVERSATION_TTL` (default 1800 seconds)
- **THEN** the Redis key SHALL expire automatically — no manual cleanup needed

#### Scenario: Conversation messages include full LLM context
- **WHEN** the LLM is called for round N
- **THEN** the messages array sent to the LLM SHALL be `[system_prompt, user_1, assistant_1, user_2, assistant_2, ..., user_N]` — the complete conversation history, because the LLM API is stateless

### Requirement: AI query API endpoint
The system SHALL expose `POST /api/ai/query` using `success_response()` helpers, registered in `contract/api_inventory.md` as `standard-json`.

#### Scenario: Successful query
- **WHEN** `POST /api/ai/query` is called with `{"question": "...", "conversation_id": "..."}`
- **THEN** the system SHALL return `success_response(data)` with `data` containing `answer` (explanation text), `chart_data` (query result), `query_used` (function name), `params_used` (parameter values), `suggestions` (drill-down prompts as Chinese text list), `conversation_id` (UUID), `round` (current round number), and `max_rounds` (5)

#### Scenario: Rate limiting
- **WHEN** a user exceeds `AI_RATE_LIMIT_MAX_REQUESTS` (default 3) requests per `AI_RATE_LIMIT_WINDOW_SECONDS` (default 60)
- **THEN** the system SHALL return a 429 response with error code `TOO_MANY_REQUESTS`

#### Scenario: LLM API timeout
- **WHEN** the LLM API does not respond within `AI_REQUEST_TIMEOUT` (default 30 seconds)
- **THEN** the system SHALL return `error_response("AI 助手回應逾時，請稍後重試", code=EXTERNAL_SERVICE_TIMEOUT, status=504)`

#### Scenario: LLM API unavailable
- **WHEN** the LLM API returns a 5xx error or connection failure
- **THEN** the system SHALL return `error_response("AI 助手暫時不可用，請使用一般查詢", code=EXTERNAL_SERVICE_ERROR, status=502)`

#### Scenario: Context limit reached
- **WHEN** the conversation exceeds round limit or token limit
- **THEN** the system SHALL return `error_response("對話已達上限，請開啟新對話", code=CONTEXT_LIMIT_REACHED, status=400)`

#### Scenario: Feature flag gating
- **WHEN** the feature flag `AI_QUERY_ENABLED` is `false`
- **THEN** the endpoint SHALL return `not_found_error("功能未啟用")`

### Requirement: Error code expansion for AI features
The system SHALL extend `core/response.py` with new predefined error code constants for AI-specific failure modes.

#### Scenario: New error codes registered
- **WHEN** the AI query feature is deployed
- **THEN** `core/response.py` SHALL define the following constants: `EXTERNAL_SERVICE_TIMEOUT`, `EXTERNAL_SERVICE_ERROR`, `CONTEXT_LIMIT_REACHED`
- **AND** SHALL provide convenience functions: `external_service_timeout_error(details)` (status 504), `external_service_error(details)` (status 502), `context_limit_error(details)` (status 400)

### Requirement: AI route layer follows thin-route contract
The AI query API route SHALL be defined in `src/mes_dashboard/routes/ai_routes.py` as a Flask Blueprint. The route SHALL only perform request parsing, rate limiting, feature flag check, service invocation, and response formatting — no business logic.

#### Scenario: Route delegates to service
- **WHEN** `POST /api/ai/query` is called
- **THEN** `ai_routes.py` SHALL parse the JSON body (`question`, `conversation_id`), apply `configured_rate_limit()`, check `AI_QUERY_ENABLED` flag, extract `user_id` from session, call `ai_query_service.process_query(user_id, question, conversation_id)`, and return the result via `success_response(data)`

#### Scenario: Route registered in API inventory
- **WHEN** the AI route is deployed
- **THEN** `contract/api_inventory.md` SHALL contain an entry for `POST /api/ai/query` under `standard-json` classification, associated with `ai_routes.py`

### Requirement: Backend proxy for LLM API
The system SHALL proxy all LLM API requests through the Flask backend. The frontend SHALL NOT call LLM APIs directly.

#### Scenario: API key stored server-side
- **WHEN** the LLM API is invoked
- **THEN** the API key SHALL be read from server-side environment variable `AI_API_KEY` — it SHALL NOT be exposed to the frontend

#### Scenario: No CSP changes required
- **WHEN** the AI query feature is enabled
- **THEN** no changes to the Content-Security-Policy `connect-src` directive SHALL be required

#### Scenario: TLS verification configurable
- **WHEN** the LLM API is called via Python `requests`
- **THEN** TLS verification SHALL be controlled by `AI_VERIFY_TLS` environment variable (default `false` due to internal network hostname mismatch)

### Requirement: Single model strategy
The system SHALL use a single LLM model (`gpt-oss:120b`) for all AI query operations.

#### Scenario: Model selection via environment variable
- **WHEN** the system is configured
- **THEN** the model SHALL be read from `AI_MODEL` environment variable (default `gpt-oss:120b`)

#### Scenario: No result summarization
- **WHEN** a query is processed
- **THEN** the LLM SHALL only perform intent parsing (question → function + params JSON); query results SHALL NOT be sent back to the LLM for summarization
- **AND** the frontend SHALL render query results directly (charts, tables, KPI cards)

### Requirement: Zero new Python dependencies
The system SHALL NOT add any new Python package dependencies for the AI query feature.

#### Scenario: HTTP calls use existing requests library
- **WHEN** the LLM API is called
- **THEN** the system SHALL use the `requests` library (already a project dependency) with OpenAI-compatible API format — no `anthropic`, `openai`, or other AI SDK dependencies SHALL be added

### Requirement: Environment variable configuration
The system SHALL support the following environment variables for AI query configuration.

#### Scenario: AI configuration in settings.py
- **WHEN** the application starts
- **THEN** `config/settings.py` SHALL read and expose the following settings:

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `AI_QUERY_ENABLED` | bool | `false` | Feature flag for AI query |
| `AI_API_URL` | str | `https://ollama_pjapi.theaken.com` | LLM API base URL |
| `AI_API_KEY` | str | (none) | LLM API key |
| `AI_MODEL` | str | `gpt-oss:120b` | LLM model ID |
| `AI_REQUEST_TIMEOUT` | int | `30` | LLM API timeout in seconds |
| `AI_VERIFY_TLS` | bool | `false` | TLS certificate verification |
| `AI_MAX_ROUNDS` | int | `5` | Max conversation rounds |
| `AI_CONTEXT_TOKEN_LIMIT` | int | `12000` | Max prompt tokens before rejection |
| `AI_MAX_TOKENS` | int | `500` | Max tokens for LLM response |
| `AI_CONVERSATION_TTL` | int | `1800` | Conversation Redis TTL in seconds |
| `AI_RATE_LIMIT_MAX_REQUESTS` | int | `3` | Rate limit requests per window |
| `AI_RATE_LIMIT_WINDOW_SECONDS` | int | `60` | Rate limit window in seconds |

#### Scenario: .env.example includes AI section
- **WHEN** the `.env.example` file is reviewed
- **THEN** it SHALL contain an `AI-Assisted Reporting — Phase 2` section with all AI environment variables, using placeholder `your-ai-api-key` for `AI_API_KEY`
