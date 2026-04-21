# Fix: Oracle ORA-* Error Codes Have No App-Level Mapping

## Why

A raw `oracledb.DatabaseError` raised from any service path propagates unhandled through Flask and lands in the generic `@app.errorhandler(Exception)` at [src/mes_dashboard/app.py:1369](../../../src/mes_dashboard/app.py#L1369), producing:

```json
{ "success": false, "error": { "code": "INTERNAL_ERROR", "message": "伺服器發生未預期的錯誤" }, "meta": { ... } }
```

…with **no ORA-code-specific mapping, no 4xx/5xx differentiation, and no `Retry-After` header**. The three ORA codes the spec calls out — 01017 (invalid credentials), 12514 (listener unknown), 01555 (snapshot too old) — are all collapsed to a 500 without any hint that the failure is recoverable, retryable, or an operator-actionable config problem.

The infrastructure to differentiate them already exists: [src/mes_dashboard/core/database.py:628](../../../src/mes_dashboard/core/database.py#L628) has `_extract_ora_code()` and [src/mes_dashboard/core/response.py](../../../src/mes_dashboard/core/response.py) has `db_connection_error` / `db_query_timeout_error` helpers. Nothing wires them together at the app level.

## Repro

Run the pinning tests in isolation (they currently pass — they assert the 500 fallthrough):

```bash
conda run -n mes-dashboard pytest --run-integration-real \
  tests/integration/test_oracle_error_path.py::TestUnmappedOraCodesFallThroughToGenericHandler -v
```

All three tests (`test_ora_01017_invalid_credential_returns_500`, `test_ora_12514_listener_returns_500`, `test_ora_01555_snapshot_returns_500`) confirm the current 500 / `INTERNAL_ERROR` behaviour via the real request path.

## Expected vs Actual

| ORA code | Current | Desired |
|---|---|---|
| ORA-01017 (invalid credentials) | 500 `INTERNAL_ERROR` | 503 `DB_CONNECTION_FAILED` (configuration issue — retries won't help, but do not leak a driver traceback) |
| ORA-12514 / 12541 (listener unknown / no listener) | 500 `INTERNAL_ERROR` | 503 `DB_CONNECTION_FAILED` + `Retry-After` (listener may recover) |
| ORA-03113 / 03135 (EOF / connection lost) | 500 `INTERNAL_ERROR` | 503 `DB_CONNECTION_FAILED` + `Retry-After` |
| ORA-01555 (snapshot too old) | 500 `INTERNAL_ERROR` | 504 `DB_QUERY_TIMEOUT` (query is too long against live undo — retryable with a smaller window) |
| ORA-01013 (user cancel) | 500 `INTERNAL_ERROR` | 499-style client-cancel or 504 (design decision — do not leak as 500) |
| other ORA-* | 500 `INTERNAL_ERROR` | 500 `DATABASE_ERROR` (not `INTERNAL_ERROR` — at least surface that it is a DB failure, not app logic) |

## What Changes

- Add an app-level Oracle-driver exception mapping at the Flask boundary.
- Route known ORA codes to contract-appropriate response helpers.
- Preserve generic exception handling for truly unknown failures.

## Suggested Fix Direction

1. Register `@app.errorhandler(oracledb.DatabaseError)` in `src/mes_dashboard/app.py` (above the generic `Exception` handler).
2. Extract the ORA code via the existing `_extract_ora_code()`.
3. Dispatch to the appropriate helper in `core/response.py`:
   - 01017 → `db_connection_error()` (503 / `DB_CONNECTION_FAILED`) — no `Retry-After` (config issue).
   - 12514 / 12541 / 03113 / 03135 → `db_connection_error(retry_after_seconds=30)` (503 + Retry-After).
   - 01555 → `db_query_timeout_error()` (504 / `DB_QUERY_TIMEOUT`).
   - Unknown ORA codes → new `database_error()` helper with `error.code = DATABASE_ERROR`, status 500, no `Retry-After`.
4. Log the ORA code + caller context at WARNING (not ERROR for known codes; ERROR for unknown) so SREs can filter oncall noise from real bugs.

Optional: introduce new typed exceptions (e.g. `OracleAuthError`, `OracleSnapshotTooOldError`) in `core/database.py` and raise them from the driver wrappers so the `@app.errorhandler` registrations become class-based rather than string-regex dispatch. That is a bigger refactor — defer unless needed.

## Acceptance

- All three pinning tests in `test_oracle_error_path.py::TestUnmappedOraCodesFallThroughToGenericHandler` **fail** with the current assertions once the mapping lands (correct outcome).
- Rewrite those three tests in the same change so they assert the new envelope (status + `error.code` + `Retry-After` per the table above). **This is intentional** — the pinning tests exist to catch the day the fix arrives, and they hand off verification of the fix to the tests that replace them.
- `_extract_ora_code()` still returns the raw digits (public contract preserved).
- No regression in happy-path Oracle queries.

## Impact

- Affects API error semantics for Oracle-originated failures.
- Improves observability and client backoff behavior without requiring a real
  Oracle instance in CI.
- May require adding one new response helper/code if unknown ORA errors should be
  distinguished from generic application failures.

## Out of Scope

- Adding a real Oracle dependency to CI (service-boundary patching stays sufficient).
- Mapping every possible ORA code — only the ones called out in the spec and the "common retryable" set from `src/mes_dashboard/core/database.py` batch-engine comments.

## Discovered By

Post-review C1 tightening of `harden-production-test-coverage`. See:
- [openspec/changes/harden-production-test-coverage/triage.md](../harden-production-test-coverage/triage.md) — "Post-Review Tightening — Round 2 (C1)" section, T014 entry.
- [tests/integration/test_oracle_error_path.py](../../../tests/integration/test_oracle_error_path.py) — the pinning tests that will flip when this change lands.
