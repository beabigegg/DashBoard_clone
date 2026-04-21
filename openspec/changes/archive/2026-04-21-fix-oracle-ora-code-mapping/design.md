## Context

The application currently has app-level handlers for pool exhaustion and
circuit-open degraded states, but raw `oracledb.DatabaseError` exceptions still
fall through to the generic Flask `Exception` handler. As a result, ORA-coded
driver failures such as invalid credentials, listener errors, or snapshot-too-
old all collapse into `500 INTERNAL_ERROR`.

The project already has two pieces of the required infrastructure:

- `_extract_ora_code()` in `core.database`
- standardized response helpers in `core.response`

What is missing is app-level dispatch that maps Oracle driver errors to stable
API semantics.

## Goals / Non-Goals

**Goals:**
- Add an app-level Oracle-driver error mapping path.
- Distinguish key ORA codes that require different client/operator behavior.
- Keep the mapping logic compatible with existing helper contracts and tests.

**Non-Goals:**
- Add a real Oracle dependency to CI.
- Create exhaustive mappings for every ORA code.
- Refactor all service layers to raise new typed Oracle exceptions in the same
  change.

## Decisions

### Map Oracle driver errors at the Flask boundary

The first implementation SHALL register an app-level handler for
`oracledb.DatabaseError` and dispatch by ORA code using `_extract_ora_code()`.
This is the lowest-cost way to cover the real request path without requiring a
cross-cutting service refactor.

Alternative considered:
- Introduce typed Oracle exceptions in all service/database wrappers first.
  Rejected for this change because it is broader and not required to fix the
  immediate response-contract bug.

### Reuse existing response helpers where semantics already fit

Known ORA codes SHALL reuse existing helpers wherever possible:

- auth/connectivity problems → `db_connection_error(...)`
- retryable query-timeout-like conditions → `db_query_timeout_error(...)`

If unknown ORA errors need a distinct machine-readable code from generic app
failures, a dedicated database-error helper/code may be introduced.

Alternative considered:
- Return `internal_error()` for unknown ORA codes.
  Rejected because it obscures the failure domain and weakens operator signals.

### Keep ORA mapping table intentionally small

The mapping table SHALL explicitly cover the ORA codes already called out by the
proposal and by existing tests first, with a sane fallback for unknown ORA
failures.

Alternative considered:
- Attempt a large ORA taxonomy immediately.
  Rejected because it increases risk and maintenance burden without immediate
  product value.

## Risks / Trade-offs

- [Dependency coupling] App-level code may need to import `oracledb` in
  environments where the driver is optional. → Mitigation: keep import guarded
  and structure tests around service-boundary patching.
- [Overfitting mappings] Incorrectly classifying an ORA code could produce the
  wrong retry semantics. → Mitigation: scope the initial mapping set narrowly and
  cover each mapped code with explicit tests.
- [Response helper gap] Unknown ORA handling may require a new helper/code. →
  Mitigation: add one only if needed to keep database-originated 500s distinct
  from generic application failures.

## Migration Plan

1. Add app-level Oracle-driver error handling above the generic exception
   handler.
2. Dispatch ORA codes using `_extract_ora_code()`.
3. Rewrite the existing Oracle pinning tests to assert the new mapped behavior.
4. Run focused integration and route tests covering ORA mapping.

Rollback: remove the Oracle-specific handler and restore the previous pinning
tests if the mapping introduces unexpected regressions.

## Open Questions

- Whether unknown ORA errors should use a new `DATABASE_ERROR` code or reuse an
  existing generic database failure helper.
- Whether ORA-01013 should be treated as timeout/degraded or a separate client-
  cancel classification.
