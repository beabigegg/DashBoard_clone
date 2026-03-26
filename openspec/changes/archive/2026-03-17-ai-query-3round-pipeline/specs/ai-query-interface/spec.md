## REMOVED Requirements

### Requirement: Multi-turn conversation management via Redis
**REMOVED** — Each question is now independent. No conversation history is maintained server-side.

Removed components:
- `_get_conversation()`, `_save_conversation()`, `_conversation_key()`, `_new_conversation_id()`
- `_estimate_tokens()` heuristic
- Redis key pattern `ai_chat:{user_id}:{conversation_id}` with TTL
- Round limit check (`round_count >= AI_MAX_ROUNDS`)
- Context token limit check (`estimated_tokens > AI_CONTEXT_TOKEN_LIMIT`)
- `OverflowError` → `CONTEXT_LIMIT_REACHED` error path

### Requirement: Conversation-related environment variables
**REMOVED** — The following settings SHALL be removed from `config/settings.py` and `.env.example`:
- `AI_MAX_ROUNDS`
- `AI_CONTEXT_TOKEN_LIMIT`
- `AI_CONVERSATION_TTL`

## CHANGED Requirements

### Requirement: AI query API endpoint
**CHANGED** — `POST /api/ai/query` request and response simplified.

#### Scenario: Request body
- **WHEN** `POST /api/ai/query` is called
- **THEN** the request body SHALL be `{"question": "..."}` only — `conversation_id` is removed

#### Scenario: Successful response
- **WHEN** the query succeeds
- **THEN** the response SHALL contain `answer` (Round 3 natural language summary), `chart_data`, `query_used`, `params_used`, `suggestions` — without `conversation_id`, `round`, or `max_rounds`

#### Scenario: Route no longer extracts user_id
- **WHEN** the route processes a request
- **THEN** it SHALL NOT extract `user_id` from session (no longer needed for conversation ownership)

#### Scenario: OverflowError handler removed
- **WHEN** the route handles exceptions
- **THEN** it SHALL NOT catch `OverflowError` (no longer raised by `process_query`)

### Requirement: process_query signature
**CHANGED** — Simplified to `process_query(question: str) -> dict`.

#### Scenario: No conversation parameters
- **WHEN** `process_query` is called
- **THEN** it SHALL accept only `question` — no `user_id` or `conversation_id` parameters

### Requirement: Error code for context limit
**CHANGED** — `CONTEXT_LIMIT_REACHED` error code and `context_limit_error()` convenience function are no longer used by AI routes. They remain in `core/response.py` for potential future use but are dead code for AI features.
