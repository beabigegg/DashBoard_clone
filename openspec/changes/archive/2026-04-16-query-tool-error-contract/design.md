## Context

`query_tool_service.py` is the heaviest service in the project. It exposes ~20 functions for lot lookup, equipment lookup, lot history, lot associations, equipment hours/lots/materials/rejects/jobs, etc. Each function follows the same error idiom: validation problems and unhandled exceptions are caught and returned as `{"error": "<chinese-or-english-message>"}` dicts, often wrapping `ValueError` or formatted exception strings (e.g., `"查詢失敗: " + str(exc)`).

The corresponding routes in `query_tool_routes.py` then check `if 'error' in result: return validation_error(result.get('error', '查詢失敗'))`. This works for the immediate semantic (something went wrong, tell the user), but it has three properties that hurt operations:

1. Every error is a 400. `cx_Oracle.DatabaseError` from a network timeout looks identical to "you forgot to fill in container_id".
2. The check is convention-only. The exploration agent flagged that `query_lot_history` at [routes/query_tool_routes.py:417-421](src/mes_dashboard/routes/query_tool_routes.py#L417) calls `success_response(result)` after the error check; if a future code path were to bypass the check, the error dict ships as a 200.
3. There is no observability on error categories. We cannot count "Oracle timeouts in the last hour" without grepping log files for the formatted message.

The same pattern repeats in `job_query_service.py` and `mid_section_defect_service.py`. This change focuses on `query_tool_service` only — once the pattern is proven, follow-up changes will migrate the rest.

## Goals / Non-Goals

**Goals:**
- Replace 54 dict-shaped error returns in `query_tool_service.py` with typed exceptions raised directly.
- Map each exception class to a single, predictable HTTP status + error code via a small route decorator.
- Make it impossible for a future route author to leak an error dict — the dict no longer exists.
- Surface Oracle timeouts as 504 (separate from user input errors) so operators can alert on them.
- Provide a regression guarantee (test or grep assertion) that `query_tool_service.py` never reintroduces `return {"error": ...}`.

**Non-Goals:**
- Migrating other services (`job_query_service`, `mid_section_defect_service`, `reject_history_service`). Out of scope.
- Changing the standard envelope shape — `core/response.py` helpers stay; only error-code vocabulary expands.
- Adding new alerting/dashboards on the new status codes — observability wiring is a follow-up.
- Internationalisation of error messages — keep current Chinese/English mix; this change is plumbing only.

## Decisions

### 1. Exception hierarchy: thin and behaviour-driven

**Decision**: One base class `MesServiceError(Exception)` with five concrete subclasses, each carrying `message: str`, optional `details: dict`, and optional `cause: Exception` (for wrapped DB errors).

```
MesServiceError
├── UserInputError       → 400 VALIDATION_ERROR
├── ResourceNotFoundError → 404 NOT_FOUND
├── QueryTimeoutError    → 504 QUERY_TIMEOUT (new code)
├── DataContractError    → 500 INTERNAL_ERROR (logged at error level)
└── InternalQueryError   → 500 INTERNAL_ERROR
```

**Alternatives considered:**
- *Single exception with a `category` attribute*: less invasive but loses pattern-matching at the route layer.
- *Reuse stdlib `ValueError` / `LookupError`*: too generic — every Python library raises these, the decorator could not distinguish service-layer intent from third-party leakage.
- *Larger taxonomy (separate `OracleTimeoutError`, `RedisTimeoutError`, ...)*: premature; we can split later if observability demands it.

The five-class taxonomy maps 1:1 to HTTP semantics and is small enough to remember.

### 2. New error code: QUERY_TIMEOUT + 504, not 503/SERVICE_UNAVAILABLE

**Decision**: Add `QUERY_TIMEOUT` constant to `core/response.py` and a `query_timeout_error()` helper returning HTTP 504. `QueryTimeoutError` exception maps to it.

**Rationale**: 504 Gateway Timeout is the precise HTTP semantic — the upstream (Oracle) did not respond in time. 503 implies the whole service is unavailable, which would be misleading and would suggest a global retry / circuit break that is not warranted for a single slow query. The new code also gives frontend and ops a clean signal to surface "查詢逾時，請縮小日期範圍" instead of a generic network error.

### 3. Route decorator, not try/except in every handler

**Decision**: Add `@map_service_errors` decorator (lives in `routes/query_tool_routes.py` initially, can be promoted to `core/` later if other route modules adopt it). Decorator catches the typed exceptions and returns the matching helper. Unknown exceptions are logged with `exc_info=True` and returned via `internal_error()`.

```python
def map_service_errors(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except UserInputError as e:
            return validation_error(e.message)
        except ResourceNotFoundError as e:
            return not_found_error(e.message)
        except QueryTimeoutError as e:
            return query_timeout_error(e.message)
        except DataContractError as e:
            logger.error("data contract error: %s", e.message, extra={"details": e.details})
            return internal_error(e.message)
        except InternalQueryError as e:
            logger.error("internal query error", exc_info=e.cause)
            return internal_error(e.message)
    return wrapper
```

**Alternatives considered:**
- *Per-handler try/except*: 7× duplication, easy to drift.
- *Flask `errorhandler(MesServiceError)` at app level*: too global — affects routes outside this change's scope and would force the migration of all services at once.

The decorator is local, opt-in per route, and trivially testable.

### 4. Refactor strategy for the 54 dict-return sites

**Decision**: Mechanical replacement, function by function. Categorisation rules:

| Original return | New raise |
|---|---|
| `return {"error": "請輸入..."} ` / `"請選擇..."` / `"請指定..."` | `raise UserInputError("...")` |
| `return {"error": "找不到..."}` (lot/equipment not found) | `raise ResourceNotFoundError("...")` |
| `except Exception as exc: return {"error": f"查詢失敗: {exc}"}` | Catch `oracledb.DatabaseError` separately, inspect `error.code` → `QueryTimeoutError` for `ORA-01013`/`ORA-12170`/`ORA-04068`. Otherwise `raise InternalQueryError("查詢失敗", cause=exc)` |
| `return {"error": "..."}` from a column-missing / KeyError on result row | `raise DataContractError("...", details={"column": "..."})` |

Routes drop the `if 'error' in result` check entirely. The result is always a success payload.

### 5. Regression guard: grep-based test

**Decision**: Add a meta-test `tests/test_query_tool_no_error_dicts.py` that opens `services/query_tool_service.py` and asserts `re.search(r'return\s+\{["\']error["\']', src)` finds zero matches. Fast, cheap, makes the contract self-enforcing across future PRs.

### 6. Out of scope: other services

**Decision**: Do not touch `job_query_service.py`, `mid_section_defect_service.py`, `reject_history_service.py` in this change. They keep the dict pattern. Each will be migrated in its own follow-up change once the query_tool migration is shipped and validated.

**Rationale**: Doing all four services at once would push the diff past 1000 lines and make review impractical. Query_tool is the largest and the most exposed to user-driven query patterns, so it is the right pilot.

## Risks / Trade-offs

- **[Frontend tolerance for 5xx]** → Oracle timeouts move from 400 to 504. If the frontend error display branches on `4xx vs 5xx`, the error message may render differently. Mitigation: audit `frontend/src/core/api.js` and the query-tool UI in the apply phase; verify the envelope is parsed identically for 4xx and 5xx.
- **[Mechanical refactor missing a site]** → 54 sites, easy to miss one. Mitigation: the regression test (decision 5) catches any leftover. Run it as part of `pytest` in tasks 6.x.
- **[Oracle exception code matching is fragile]** → Mapping `ORA-01013`/`ORA-12170` to timeout assumes those are the only timeout codes we see. If the driver wraps them differently, we may misclassify. Mitigation: catch broadly first as `oracledb.DatabaseError` → `InternalQueryError`, then refine timeout detection in a follow-up if logs show miscategorisation.
- **[Out-of-scope services still have the bad pattern]** → Three other services keep returning error dicts. Code reviewers may be confused by the inconsistency. Mitigation: explicit "out of scope" callout in this proposal + a tracking issue for follow-up changes.
- **[Test mocks need rewriting]** → Existing tests in `test_query_tool_routes.py` mock services to return `{"error": "..."}`. They must be rewritten to raise the new exceptions. This is mechanical but tedious.

## Migration Plan

1. Land `core/exceptions.py` and `core/response.py` additions first as a tiny precursor commit (no behaviour change). Verify CI is green.
2. Land `query_tool_service.py` refactor + `query_tool_routes.py` decorator + test rewrite as a single PR. The diff is large but cohesive.
3. Run the regression grep test in CI from the moment the second PR lands.
4. Manually exercise the 7 query-tool routes against a real backend: malformed input (expect 400), valid query (expect 200), forced timeout via `ALTER SESSION SET ddl_lock_timeout = 1` or similar (expect 504).
5. Open follow-up issues for `job_query_service`, `mid_section_defect_service`, `reject_history_service` migrations, referencing this change as the template.

**Rollback**: revert the second PR. The first PR (precursor) is harmless on its own — it only adds an unused exception class and an unused error code. No data migration.

## Open Questions

*(none — both decisions resolved during planning)*
