# Fix: `map_service_errors` Swallows DatabaseDegradedError Subclasses

## Why

The `@map_service_errors` decorator at [src/mes_dashboard/routes/query_tool_routes.py:48-90](../../../src/mes_dashboard/routes/query_tool_routes.py#L48-L90) catches typed service exceptions and maps them to specific response helpers. **But it also has a catch-all `except Exception` at line 83 that returns `internal_error()` (500 / `INTERNAL_ERROR`) for everything else** — including `DatabasePoolExhaustedError` and `DatabaseCircuitOpenError`.

Both degraded-state exceptions have dedicated app-level handlers at [src/mes_dashboard/app.py:1351-1367](../../../src/mes_dashboard/app.py#L1351-L1367) that respond **503 + `Retry-After`** per the degraded-response contract. The decorator never lets those exceptions escape, so the app-level handlers never run for any query-tool route.

**User-visible impact**: when the database pool is exhausted or the breaker is open, users hitting **any** query-tool route (`/api/query-tool/resolve`, `/api/query-tool/lot-equipment-lookup`, `/api/query-tool/export-csv`, …) receive:

- ❌ `500 INTERNAL_ERROR` with a generic "伺服器發生未預期的錯誤" message — instead of the spec-required `503 DB_POOL_EXHAUSTED` / `503 CIRCUIT_BREAKER_OPEN`.
- ❌ **No `Retry-After` header** — clients can't back off intelligently; naive retry storms can deepen pool exhaustion.

The resource-history blueprint, which does not use this decorator, responds correctly (proven by [tests/integration/test_oracle_error_path.py::TestDegradedContractViaResourceHistoryRoute](../../../tests/integration/test_oracle_error_path.py)).

## Repro

```bash
conda run -n mes-dashboard pytest --run-integration-real \
  tests/integration/test_oracle_error_path.py::TestMapServiceErrorsSwallowsDegradedErrors -v
```

Both tests pin the current (wrong) 500 behaviour. They pass today; they will fail once this change lands.

## Expected vs Actual

| Scenario | Route | Current | Desired |
|---|---|---|---|
| Pool exhausted | `/api/query-tool/*` (any) | 500 `INTERNAL_ERROR`, no `Retry-After` | 503 `DB_POOL_EXHAUSTED` + `Retry-After: 5` |
| Circuit open | `/api/query-tool/*` (any) | 500 `INTERNAL_ERROR`, no `Retry-After` | 503 `CIRCUIT_BREAKER_OPEN` + `Retry-After: 30` |
| Pool exhausted | `/api/resource/history/options` | 503 + `Retry-After` ✓ | unchanged |

## What Changes

- Preserve the existing typed service-error mapping behavior.
- Stop converting degraded database exceptions into generic 500s.
- Let `DatabasePoolExhaustedError` and `DatabaseCircuitOpenError` reach the
  existing app-level Flask error handlers.

## Suggested Fix Direction

Insert a re-raise branch near the top of the decorator, before the catch-all. Change from:

```python
@wraps(fn)
def wrapper(*args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except UserInputError as e:
        ...
```

to:

```python
from mes_dashboard.core.database import DatabaseDegradedError

@wraps(fn)
def wrapper(*args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except DatabaseDegradedError:
        # Let the app-level @errorhandler(DatabasePoolExhaustedError) /
        # @errorhandler(DatabaseCircuitOpenError) respond with the
        # degraded-response envelope + Retry-After.
        raise
    except UserInputError as e:
        ...
```

Rationale: `DatabaseDegradedError` is the common base class for both `DatabasePoolExhaustedError` and `DatabaseCircuitOpenError` ([src/mes_dashboard/core/database.py:128-132](../../../src/mes_dashboard/core/database.py#L128-L132)), so one re-raise clause covers both plus any future subclass.

**Alternative**: replace the `except Exception` catch-all with an `except (DataContractError, InternalQueryError, ...) as e` tuple of the known types and let `Exception` fall through naturally. That is a bigger change (loses the "log unexpected" path) — defer unless the minimal fix proves insufficient.

## Acceptance

- Both pinning tests in `test_oracle_error_path.py::TestMapServiceErrorsSwallowsDegradedErrors` **fail** with the current pinning assertions (expected outcome).
- Rewrite them in the same change to assert the new 503 envelope + `Retry-After` (mirror the resource-history tests).
- Manually verify: `curl -s -o /dev/null -w '%{http_code} %{header:retry-after}\n' …` against a query-tool route under forced pool-exhaustion returns `503 5`.
- No regression in the typed-exception branches (`UserInputError`, `ResourceNotFoundError`, etc.) — existing route tests must stay green.

## Impact

- Affects all query-tool routes using `@map_service_errors`.
- No schema or payload change for happy-path responses.
- Invalid current degraded responses (`500 INTERNAL_ERROR`) become contract-correct
  `503` responses with `Retry-After`, which is an intentional behavioral fix.

## Out of Scope

- Auditing other decorators in the codebase for the same anti-pattern (separate hygiene pass).
- Adding a ResourceHistoryServiceError family — this fix touches only the query-tool decorator.

## Discovered By

Post-review C1 tightening of `harden-production-test-coverage`. See:
- [openspec/changes/harden-production-test-coverage/triage.md](../harden-production-test-coverage/triage.md) — "Post-Review Tightening — Round 2 (C1)" section, T015 entry.
- [tests/integration/test_oracle_error_path.py](../../../tests/integration/test_oracle_error_path.py) — the pinning tests that will flip when this change lands (mutation M15 already proved this dynamically).
