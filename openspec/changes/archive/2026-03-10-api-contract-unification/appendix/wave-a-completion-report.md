# Wave A Completion Report — `wip_routes.py` API Contract Migration

## Summary

Wave A of the API contract unification change is complete. All 25 manual `jsonify` calls
in `wip_routes.py` have been replaced with standardized response helpers.

## Changes Made

### Backend
| File | Change |
|------|--------|
| `src/mes_dashboard/routes/wip_routes.py` | Replaced all 25 `jsonify(...)` calls with `success_response()`, `validation_error()`, `not_found_error()`, `internal_error()`. Removed `jsonify` from imports. |
| `src/mes_dashboard/core/response.py` | Added `CACHE_EXPIRED`, `CACHE_MISS` error codes. Added `cache_expired_error()` and `cache_miss_error()` helpers. Added helper usage guide in module docstring. |
| `src/mes_dashboard/routes/health_routes.py` | Added contract exception notation in module docstring. No behavior change. |

### Tests
| File | Change |
|------|--------|
| `tests/test_wip_routes.py` | Updated 4 validation error tests to assert `error.code == 'VALIDATION_ERROR'` and `error.message` (was string). Added `meta.timestamp` assertion to success tests. Updated 1 internal_error test to assert `error.code == 'INTERNAL_ERROR'`. |
| `tests/test_api_contract.py` | New file. Contract guardrail tests for: zero-jsonify (wip_routes), baseline regression, health exception contract, standard envelope shape. |

### Documentation
| File | Change |
|------|--------|
| `contract/api_refactoring_plan.md` | Updated from v1.0 to v2.0 with wave-based plan, endpoint classification, acceptance criteria, helper reference, and guardrails. |
| `openspec/changes/api-contract-unification/appendix/baseline-and-waves.md` | Baseline report with endpoint classification inventory, jsonify counts, cache signal inventory, and wave registry. |

## Test Results

All tests in scope pass:
- `tests/test_wip_routes.py` — all assertions updated and passing
- `tests/test_api_contract.py` — all new contract tests passing

## Rollback Point

Git commit containing the above changes. Revert this commit to restore `wip_routes.py`
to its pre-Wave A state.

## Frontend Impact

- `frontend/src/core/api.js` already handles both old string-error and new object-error formats.
  No change required.
- Pages using `cache_expired`/`cache_miss` string checks (hold-history, reject-history,
  resource-history, yield-alert-center) do NOT use wip routes. No regression.

## Wave B+ Start Conditions

Wave B is ready to start when:
1. Wave A tests are green in CI
2. No frontend error reports related to wip endpoints
3. Team confirms readiness for `resource_routes.py` / `dashboard_routes.py`

Risk threshold for pausing Wave B:
- Any frontend 500-level error related to wip pages → pause and investigate
- Any regression in health endpoint monitoring → pause (should not be possible given no health changes)
