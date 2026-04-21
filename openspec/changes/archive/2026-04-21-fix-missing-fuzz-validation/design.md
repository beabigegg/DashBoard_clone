## Context

Three existing endpoints currently accept malformed inputs and return `200`
empty-success responses instead of validation errors:

- `/api/reject-history/options`
- `/api/hold-overview/summary`
- `/api/wip/overview/summary`

This was surfaced by the strict fuzz suite added in
`harden-production-test-coverage`. The current route behavior is inconsistent
with the project's API contract and with other hardened endpoints that reject
bad input early using `validation_error(...)`.

The change is cross-cutting across multiple routes, but the underlying design
problem is the same: route boundaries do not enforce basic validation for date
and filter fields before invoking downstream query logic.

## Goals / Non-Goals

**Goals:**
- Reject malformed date/filter inputs at the route boundary with a standardized
  validation envelope.
- Align all three affected endpoints with the project's response contract.
- Remove the temporary `xfail` markers in strict fuzz tests once validators are
  in place.

**Non-Goals:**
- Redesign the semantics of valid business filters.
- Enforce blanket ASCII-only rules on every text field.
- Refactor every route validator in the codebase in the same change.

## Decisions

### Validate at the route boundary, before service execution

The affected routes SHALL validate query params before they enter deeper query
or service layers. This preserves the distinction between invalid input and
"valid request with no matching data".

Alternative considered:
- Let the service/query layer absorb invalid inputs and return empty data.
  Rejected because it hides invalid requests as successful queries and weakens
  the API contract.

### Use shared validation helpers for repeated rules

Date parsing, inverted-range checks, and common text-filter hygiene SHALL be
centralized in shared helpers where practical so the three routes do not drift.

Alternative considered:
- Copy validation snippets into each route.
  Rejected because it invites inconsistent rules and error messages.

### Return failures via response helpers only

All invalid-input responses SHALL use `mes_dashboard.core.response.validation_error()`
instead of manual JSON responses. This keeps the envelope and metadata
consistent with project conventions.

Alternative considered:
- Manual `jsonify` or per-route error payloads.
  Rejected due to explicit project contract constraints.

## Risks / Trade-offs

- [Over-rejection] A filter sanitizer could reject values that are valid for a
  specific business field. → Mitigation: keep checks field-aware and focused on
  clearly invalid shapes (null byte, whitespace-only, malformed dates, obvious
  control/meta patterns).
- [Behavior change for existing clients] Some clients may currently interpret
  empty data as success for malformed inputs. → Mitigation: document the API
  behavior change and keep the new failure mode machine-readable.
- [Validator drift] If only these three routes are fixed, nearby routes may
  remain inconsistent. → Mitigation: use shared helpers so future adoption is
  simpler.

## Migration Plan

1. Add or extract shared validators for the affected query params.
2. Apply those validators to the three affected routes.
3. Return `validation_error(...)` on rejection.
4. Remove `xfail` markers from the strict fuzz tests.
5. Run route fuzz and focused happy-path route tests.

Rollback: restore the previous route behavior and reapply `xfail` markers in the
fuzz tests if a validator is found to be too aggressive.

## Open Questions

- Whether `workcenter_group` should allow the full Unicode set used by
  workcenter labels or a stricter business-defined subset.
- Whether the same helper should be adopted immediately by neighboring Hold/WIP
  filter endpoints in a follow-up hygiene pass.
