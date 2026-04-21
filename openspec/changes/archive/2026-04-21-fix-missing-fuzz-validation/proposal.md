# Fix: Missing Input Validation on Fuzz-Flagged Endpoints

## Why

Three production endpoints currently accept malformed inputs and return `200`
with empty data instead of rejecting them with a validation envelope. This is
not just a test-quality issue; it means user input that should be rejected
early is silently allowed to flow deeper into the query path.

That has three costs:

- Invalid or malicious-looking input is indistinguishable from a legitimate
  "no results" query.
- The UI cannot surface actionable validation feedback because the backend says
  the request succeeded.
- Future query-layer changes may turn these currently silent cases into real 500s
  because the route contract is not enforcing input boundaries.

These gaps were surfaced by the strict fuzz suite added in
`harden-production-test-coverage`. The affected tests are currently marked
`xfail(strict=False)` so the regressions stay visible while the product bug is
tracked separately.

## Affected Endpoints

| Endpoint | Method | Missing validator for |
|---|---|---|
| `/api/reject-history/options` | GET | `start_date`, `end_date` |
| `/api/hold-overview/summary` | GET | `workcenter_group` |
| `/api/wip/overview/summary` | GET | `workcenter_group` |

## Repro

```bash
conda run -n mes-dashboard pytest tests/routes/test_fuzz_routes.py -v
```

Current tracked failures are the `xfail` cases for:

- `test_reject_history_options_rejects_malicious_start_date`
- `test_hold_overview_rejects_malicious_filter`
- `test_wip_rejects_malicious_filter`

Across 24 fuzz cases, these endpoints currently accept payloads such as:

- SQL-style payloads
- 100k-character strings
- null-byte strings
- whitespace-only values
- inverted dates
- negative pagination shapes encoded as payloads
- Unicode / emoji edge cases
- CSV-injection style `=...` prefixes

## Expected vs Actual

| | Behaviour |
|---|---|
| **Expected** | Invalid input is rejected at the route boundary with `400/422` and `error.code == 'VALIDATION_ERROR'` using `core/response.py` helpers. |
| **Actual** | The route accepts the malformed input, falls through to downstream query logic, and returns `200 success:true` with an empty dataset. |

## What Changes

- Add explicit validation at the route boundary for the affected query params.
- Standardize these failures on the project envelope contract:
  `validation_error(...)`.
- Remove the temporary `xfail` markers from the strict fuzz tests once the
  endpoints satisfy the contract.

## Suggested Fix Direction

1. Add shared validation helpers where the same input rules repeat across
   routes. Avoid copying slightly different regexes into each handler.
2. For date parameters:
   - validate presence/format with strict `YYYY-MM-DD` parsing
   - reject inverted ranges (`start_date > end_date`)
3. For free-text filters such as `workcenter_group`:
   - reject whitespace-only values
   - apply a reasonable length cap
   - reject null bytes and obviously invalid control/meta patterns
   - keep Unicode support only if the field semantically allows it
4. Return failures via `mes_dashboard.core.response.validation_error()` rather
   than ad hoc JSON.

## Acceptance

- All 24 previously `xfail` fuzz cases pass as strict validation failures.
- The three `@pytest.mark.xfail` annotations are removed from
  `tests/routes/test_fuzz_routes.py`.
- The responses are `400/422`, valid JSON, `success: false`, and
  `error.code == 'VALIDATION_ERROR'`.
- Normal happy-path values still return `200` and unchanged payload shape.

## Impact

- Affects request validation in three existing route handlers.
- No intended frontend changes beyond improved user-visible validation behavior.
- Small API behavior change for invalid inputs: callers that currently interpret
  empty data as success will now receive validation errors instead.

## Out of Scope

- Broad refactors of all query validators across the codebase.
- Reclassifying every Unicode input as invalid; rules should remain field-driven,
  not blanket ASCII-only unless the field contract demands it.

## Discovered By

Post-review tightening of `harden-production-test-coverage`, documented in:

- `openspec/changes/harden-production-test-coverage/triage.md`
- `openspec/changes/harden-production-test-coverage/proposal.md`
