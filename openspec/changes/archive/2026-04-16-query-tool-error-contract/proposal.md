## Why

`services/query_tool_service.py` returns error states as plain dicts (`{"error": "查詢失敗: ORA-12170..."}`) in 54 places across ~20 functions. Routes consume these via `if 'error' in result: return validation_error(...)`, which has three problems:

1. **Semantic conflation** — Oracle timeouts, schema drift, missing parameters, and user-typed nonsense all collapse to a single string and a single 400 status code. Operators cannot tell from the response whether the user typed it wrong or the database is on fire.
2. **Brittle by convention** — every new route author must remember the `if 'error' in result` check. Forgetting it (and one already-flagged risk site exists at [query_tool_routes.py:417-421](src/mes_dashboard/routes/query_tool_routes.py#L417)) leaks the error dict back as a 200 success.
3. **Untyped** — there is no way to assert in tests "this should have raised QueryTimeout"; only string matching is possible.

The fix is to introduce typed service-layer exceptions and a route-level decorator that maps each exception class to the right `core/response.py` helper. Routes stop checking for the magic key. Services stop building error dicts.

## What Changes

- **NEW** `src/mes_dashboard/core/exceptions.py` defines a small exception hierarchy:
  - `MesServiceError` (base)
  - `UserInputError` → 400 `VALIDATION_ERROR`
  - `ResourceNotFoundError` → 404 `NOT_FOUND`
  - `QueryTimeoutError` → 504 `QUERY_TIMEOUT` (new error code, see below)
  - `DataContractError` → 500 `INTERNAL_ERROR`, logs at error level (signals schema drift)
  - `InternalQueryError` → 500 `INTERNAL_ERROR`
- **NEW** error code constant `QUERY_TIMEOUT` and helper `query_timeout_error()` in `core/response.py` returning HTTP 504.
- **NEW** `@map_service_errors` decorator in `routes/query_tool_routes.py` (or a shared helper) that catches the typed exceptions and converts to the right response helper. Unknown exceptions are logged and returned via `internal_error()`.
- **MODIFIED** `services/query_tool_service.py` — all 54 `return {"error": ...}` sites refactored to `raise UserInputError(...)`, `raise QueryTimeoutError(...)`, etc. Oracle/database exceptions caught at the bottom of try blocks are categorised: `oracledb.DatabaseError` with `ORA-01013/ORA-12170` codes → `QueryTimeoutError`; `KeyError`/missing column → `DataContractError`; everything else → `InternalQueryError(cause=exc)`.
- **MODIFIED** all 7 route handlers in `routes/query_tool_routes.py` — wrapped with `@map_service_errors`. Every existing `if 'error' in result` check is removed.
- **REGRESSION GUARD** — a grep-based assertion (in tests or as a CI check) that `services/query_tool_service.py` contains zero `return {"error":` patterns post-refactor.
- **OUT OF SCOPE** — `job_query_service.py`, `mid_section_defect_service.py`, `reject_history_service.py` keep their dict-error pattern in this change; they will be migrated in follow-up changes once this approach is proven on query_tool.

## Capabilities

### New Capabilities
- `query-tool-service-error-contract`: typed service-layer exceptions, exception-to-HTTP mapping, regression guarantee that error states never leak as 200 success.

### Modified Capabilities
- `api-response-contract-unification`: adds the `QUERY_TIMEOUT` error code and `query_timeout_error()` helper to the standardised error envelope vocabulary.

## Impact

- **Affected code**:
  - `src/mes_dashboard/core/exceptions.py` (new, ~80 lines)
  - `src/mes_dashboard/core/response.py` (add `QUERY_TIMEOUT` constant + helper, ~10 lines)
  - `src/mes_dashboard/services/query_tool_service.py` (54 refactor sites)
  - `src/mes_dashboard/routes/query_tool_routes.py` (decorator + 7 handlers, removal of dict checks)
  - `tests/test_query_tool_error_contract.py` (new, ~200 lines)
  - `tests/test_query_tool_routes.py`, `tests/test_query_tool_service.py` (rewrite expectations to match exceptions instead of dicts)
- **API contract**: status codes for some error paths change. Oracle timeouts move from 400 → 504. Internal exceptions move from 400 → 500. Frontend error display must tolerate 5xx with the same envelope shape (it should, but verify). User-input errors stay at 400.
- **Frontend**: audit `frontend/src/core/api.js` and any query-tool UI error display path to confirm 504/500 responses surface a useful message instead of generic "Network Error".
- **Operational**: 504/500 responses are now meaningful signals — wire them into the existing error logging/metrics if not already there.
- **Dependencies**: none added.
