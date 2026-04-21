## Context

`routes/query_tool_routes.py` uses the `@map_service_errors` decorator to
translate typed service exceptions into HTTP responses. The decorator correctly
handles the known service-error classes but currently also catches
`DatabasePoolExhaustedError` and `DatabaseCircuitOpenError` via a broad
`except Exception`, converting them to generic `500 INTERNAL_ERROR`.

That is a contract violation because the Flask app already has app-level
handlers for these degraded database states that produce retry-aware `503`
responses with `Retry-After`.

The change is localized to error propagation policy in the decorator and the
tests that assert degraded response behavior on query-tool routes.

## Goals / Non-Goals

**Goals:**
- Preserve the existing decorator behavior for typed query-tool service errors.
- Allow degraded database exceptions to propagate to app-level handlers.
- Convert query-tool degraded responses from generic 500s to contract-correct
  retry-aware 503s.

**Non-Goals:**
- Redesign the entire query-tool service exception hierarchy.
- Audit every decorator in the codebase for similar patterns.
- Change happy-path query-tool responses.

## Decisions

### Re-raise the common degraded base class

The decorator SHALL explicitly re-raise `DatabaseDegradedError` before the broad
catch-all. This covers both existing degraded subclasses and future ones without
enumerating each concrete class in the decorator.

Alternative considered:
- Re-raise each degraded subclass individually.
  Rejected because it is easier to forget new subclasses and duplicates the type
  hierarchy knowledge already captured by the base class.

### Keep the broad catch-all for truly unexpected exceptions

The generic `except Exception` branch SHALL remain in place for non-degraded,
non-typed exceptions so the route still logs and returns `internal_error()` for
unexpected failures.

Alternative considered:
- Remove the catch-all entirely.
  Rejected because it changes existing observability and failure semantics for
  unrelated unexpected exceptions.

## Risks / Trade-offs

- [Too-broad re-raise] If non-retryable exceptions are later subclassed from
  `DatabaseDegradedError` incorrectly, they may bypass the decorator. →
  Mitigation: keep the degraded hierarchy narrowly defined in `core.database`.
- [Behavior shift for clients] Some clients may implicitly expect 500 from these
  query-tool routes today. → Mitigation: the new behavior aligns with the
  documented degraded contract and improves backoff handling.
- [Test flip management] Existing pinning tests will need to be rewritten once
  the fix lands. → Mitigation: make that rewrite part of the same change.

## Migration Plan

1. Import `DatabaseDegradedError` into the query-tool route decorator module.
2. Add a re-raise branch before the broad `except Exception`.
3. Replace pinning tests with assertions for the new `503 + Retry-After`
   behavior.
4. Run focused query-tool route/integration tests.

Rollback: remove the re-raise branch and restore the prior pinning tests if the
change causes unexpected propagation behavior.

## Open Questions

- Whether any non-query-tool decorators should adopt the same propagation policy
  in a separate hygiene pass.
