## 1. Precursor: exception hierarchy and new error code

- [x] 1.1 Create `src/mes_dashboard/core/exceptions.py`. Define `MesServiceError(Exception)` base with `message`, `details`, `cause` attributes. Add subclasses `UserInputError`, `ResourceNotFoundError`, `QueryTimeoutError`, `DataContractError`, `InternalQueryError`. Each subclass takes `(message, details=None, cause=None)` and stores them.
- [x] 1.2 Add `QUERY_TIMEOUT = "QUERY_TIMEOUT"` constant to `src/mes_dashboard/core/response.py`. Add `query_timeout_error(message, details=None)` helper that returns `error_response(QUERY_TIMEOUT, message, details=details, status_code=504)`.
- [x] 1.3 Add unit test `tests/test_core_exceptions.py` covering: subclass instantiation with all three kwargs, `str()` returns message, `cause` chains correctly when re-raised.
- [x] 1.4 Add unit test `tests/test_query_timeout_helper.py` asserting envelope shape and 504 status.
- [x] 1.5 Run `pytest tests/test_core_exceptions.py tests/test_query_timeout_helper.py -v` — green.

## 2. Decorator: map_service_errors

- [x] 2.1 Add `map_service_errors` decorator to `src/mes_dashboard/routes/query_tool_routes.py` (top of file, after imports). Catch each exception class and return the matching helper. Log `DataContractError` and `InternalQueryError` with `logger.error(..., exc_info=cause)`. Catch the bare `Exception` last → log + `internal_error()`.
- [x] 2.2 Add unit test `tests/test_map_service_errors_decorator.py`. Use a fake handler that raises each exception class in turn and assert the response envelope and status code.

## 3. Refactor query_tool_service.py: validation paths

- [x] 3.1 `resolve_lots()` (lines ~514, 517, 522, 538, 560, 565) — replace each validation error dict return with `raise UserInputError(...)`.
- [x] 3.2 `_resolve_by_gd_lot_id()` (line ~671), `_resolve_by_gd_work_order()` (line ~892), `_resolve_by_work_order()` (line ~849) — same.
- [x] 3.3 `get_lot_history()` (line ~1057), `get_lot_history_batch()` (lines ~1179, 1182, 1269) — validation paths to `UserInputError`.
- [x] 3.4 `get_lot_associations_batch()` (lines ~1289, 1292, 1296), `get_lot_materials/rejects/holds()` (lines ~1394, 1434, 1475) — same.
- [x] 3.5 `get_lot_splits()` (line ~1533), `get_lot_jobs()` (line ~1797), `get_lot_jobs_with_history()` (line ~1855) — same.
- [x] 3.6 `resolve_lot_equipment()` (lines ~2121–2135), `get_equipment_status_hours()` (lines ~2264, 2268), `get_equipment_lots()` (lines ~2359, 2363), `get_equipment_materials/rejects/jobs()` (lines ~2418, 2471, 2526) — same.

## 4. Refactor query_tool_service.py: exception-catch paths

- [x] 4.1 For every `except Exception as exc:` block that returned `{"error": "查詢失敗: ..."}` (lines ~565, 1102, 1269, 1375, 1419, 1460, 1499, 1610, 1832, 1892, 2237, 2335, 2397, 2450, 2503, 2555):
  - Catch `oracledb.DatabaseError` (or `cx_Oracle.DatabaseError`) separately first.
  - Inspect the error code; if it matches a known timeout (`ORA-01013`, `ORA-12170`, `ORA-04068`) → `raise QueryTimeoutError("查詢逾時，請縮小範圍", cause=exc)`.
  - Otherwise (and for the outer `Exception` block) → `raise InternalQueryError("查詢失敗", cause=exc)`.
- [x] 4.2 For any site that matches a column-missing or KeyError pattern on result rows → `raise DataContractError("缺少欄位 X", details={"column": "X"})`.
- [x] 4.3 For "找不到 LOT/設備" patterns (if any) → `raise ResourceNotFoundError(...)`.
- [x] 4.4 Verify with grep: `grep -n 'return\s*{["'\'']*error' src/mes_dashboard/services/query_tool_service.py` — expect 0 matches.

## 5. Wrap routes and remove dict checks

- [x] 5.1 Apply `@map_service_errors` to each of the 7 route handlers in `routes/query_tool_routes.py`: `query_resolve` (~343), `query_lot_history` (~360), `query_adjacent_lots` (~430), `query_lot_associations` (~528), `query_equipment_period` (~614), `query_lot_equipment_lookup` (~731), `query_export_csv` (~910).
- [x] 5.2 In each handler, delete the `if 'error' in result: return validation_error(...)` line. The result is now always a success payload.
- [x] 5.3 Audit the post-error-check code paths (e.g., `query_lot_history` lines 417–421 with the `gc.collect()` call) — make sure they still execute correctly when no error key exists.

## 6. Regression and integration tests

- [x] 6.1 New test `tests/test_query_tool_no_error_dicts.py` — open `services/query_tool_service.py`, run `re.search(r"return\s*\{['\"]error['\"]", src)`, assert `is None`. **This is the canonical regression guard.**
- [x] 6.2 New test file `tests/test_query_tool_error_contract.py`. For each of the 7 routes:
  - monkeypatch the underlying service to raise `UserInputError` → assert 400 + `VALIDATION_ERROR`
  - raise `ResourceNotFoundError` → assert 404 + `NOT_FOUND`
  - raise `QueryTimeoutError` → assert 504 + `QUERY_TIMEOUT`
  - raise `DataContractError` → assert 500 + `INTERNAL_ERROR` + log captured
  - raise `InternalQueryError(cause=ValueError("x"))` → assert 500 + `INTERNAL_ERROR` + traceback in logs
  - raise bare `RuntimeError` → assert 500 + `INTERNAL_ERROR` + log captured
  - return normal payload → assert 200 + envelope unchanged
- [x] 6.3 Update `tests/test_query_tool_service.py` — replace any `assert "error" in result` with `pytest.raises(UserInputError)` etc.
- [x] 6.4 Update `tests/test_query_tool_routes.py` — replace mocks that return `{"error": "..."}` with mocks that raise the matching exception.
- [x] 6.5 Run `pytest tests/test_query_tool*.py tests/test_core_exceptions.py tests/test_query_timeout_helper.py tests/test_map_service_errors_decorator.py -v` — green.

## 7. Frontend audit (no functional changes expected)

- [x] 7.1 Read `frontend/src/core/api.js` to confirm the response interceptor parses the error envelope identically for 4xx and 5xx responses (it should — both follow the same shape).
- [ ] 7.2 Open the query-tool page in a dev server, force a `UserInputError` (submit empty form) and verify the existing error toast renders. Force an `InternalQueryError` (kill Oracle / unset DSN) and verify the user sees a meaningful message instead of "Network Error".
- [ ] 7.3 If the frontend branches on status code 4xx vs 5xx anywhere, confirm 504 is treated as "user-actionable retry" not "fatal".

## 8. Verification

- [x] 8.1 `pytest tests/ -v -k "query_tool or core_exceptions or query_timeout or map_service_errors"` — all green.
- [x] 8.2 `grep -rn 'return\s*{["'\'']*error' src/mes_dashboard/services/query_tool_service.py` returns nothing.
- [ ] 8.3 Manual smoke test in dev: each of the 7 routes hit at least once with valid input → 200; with malformed input → 400; with simulated DB outage (stop Oracle listener) → 500 or 504.
- [ ] 8.4 `openspec validate query-tool-error-contract --strict` passes.
- [ ] 8.5 Open follow-up tracking issues for migrating `job_query_service.py`, `mid_section_defect_service.py`, `reject_history_service.py` to the same pattern (out of scope for this change).
