# Archive: rh-primary-prefilter

## Change Summary

Added three optional primary prefilter controls (PJ Type, Package, PJ Function) to reject-history.
The filters are applied at the Oracle BASE_WHERE level — before chunking, before the reject-specific
WHERE clause — so they reduce server load on large date ranges instead of post-filtering results.
All four query paths (sync route, cache-key/spool-key, legacy async job, unified async job) were
updated in one change to guarantee sync/async parity (RHPF-05).

## Final Behavior

- GET `/api/reject-history/filter-options` returns `pj_types`, `packages`, `pj_functions` lists
  (cross-filtered by the other two dimensions).
- POST `/api/reject-history/query` accepts optional `pj_types`, `packages`, `pj_functions` arrays;
  each non-empty array injects an `IN (…)` clause into Oracle BASE_WHERE.
- Frontend FilterPanel shows three MultiSelect dropdowns in the primary query section; options refresh
  on mount (empty selection) and debounce 200 ms after each dropdown-close event; selections that
  disappear from new options are pruned silently (fail-open).
- PJ_BOP filter is intentionally excluded (AC-6).

## Final Contracts Updated

- `contracts/api/api-contract.md` — `POST /api/reject-history/query` extended with three optional params
- `contracts/api/openapi.json` + `contracts/openapi.json` — regenerated with new optional fields
- `contracts/data/data-shape-contract.md` — RejectHistoryQueryInput schema extended
- `contracts/business/business-rules.md` — RH-PRIMARY-PREFILTER-01..04 rules added

Evidence: backend-engineer.yml artifacts §contracts-touched; ci-cd-gatekeeper.yml §gate-promotions

## Final Tests Added / Updated

| file | new tests |
|---|---|
| `tests/test_reject_history_service.py` | 12 (build_where_clause + pj_bop-absent SQL paths) |
| `tests/test_reject_history_routes.py` | 6 (route prefilter forwarding) |
| `tests/test_reject_history_async_routes.py` | 5 (async prefilter forwarding) |
| `tests/test_reject_dataset_cache.py` | 7 (cache-key parity + execute_primary_query forwarding) |
| `tests/test_reject_query_job_service.py` | 4 (legacy async job param forwarding) |
| `frontend/tests/validation/useRejectHistory.validation.test.js` | 10 (FilterPanel payload assertions) |
| `frontend/tests/playwright/reject-history-filter.spec.ts` | multi-block (E2E FilterPanel render + payload) |

Evidence: backend-engineer.yml §tests-added, §test-output; frontend-engineer.yml §test-runs; test-evidence.yml

## Final CI/CD Gates

All gates pre-existing; no new workflow file. Tier-2 additive change.

| gate | result |
|---|---|
| contract-validate (cdd-kit validate) | pass |
| response-shape-validate | pass |
| unit-mock-integration (173 backend) | pass |
| frontend-unit (626 frontend) | pass |
| css-governance | pass |
| cdd-kit gate rh-primary-prefilter | pass |

Evidence: ci-cd-gatekeeper.yml; test-evidence.yml; ci-gates.md

## Production Reality Findings

1. **Exact-limit date boundary trap**: Pre-existing test `test_query_rejects_date_range_over_half_year`
   used `2025-01-01..2025-12-31` (exactly 365 days = env default limit), so it passed validation and
   reached the enqueue path instead of the expected rejection. Fixed to `2024-01-01..2025-03-01`
   (>365 days) with a `天` message assertion. Rule: "over-limit" tests must exceed the limit strictly.
   Evidence: backend-engineer.yml §known-risks #3; commit `6988392b`.

2. **Container mode uses separate injection path**: Container-mode queries have no date params and a
   different base SQL structure, so prefilters are injected inline inside `execute_primary_query` rather
   than via `_build_base_where`. The two paths are intentionally divergent.
   Evidence: backend-engineer.yml §known-risks #2.

3. **Chunk bind param ordering**: In the unified job, chunk bind params (`start_date`, `end_date`) are
   built first, then prefilter binds are applied via `dict.update()`. This natural ordering ensures chunk
   dates are not overridden by prefilter params even if they share key names.
   Evidence: backend-engineer.yml §known-risks #1.

## Lessons Promoted to Standards

**Promoted to `CLAUDE.md` Test coverage discipline + `docs/architecture/test-discipline.md`:**

- **Over-limit boundary tests must strictly exceed the cap** — equal-to-cap inputs pass validation silently and route to the success path; the test asserts the wrong code branch.
  - Evidence: backend-engineer.yml §known-risks #3; commit `6988392b`
  - CLAUDE.md line added under `**Test coverage discipline**` inside `cdd-kit:learnings` markers
  - Detail added to `docs/architecture/test-discipline.md` §Over-Limit Boundary Tests Must Strictly Exceed the Cap

**Not promoted:**
- Chunk bind param ordering (dict.update() natural ordering — self-documenting code)
- Container mode inline injection (implementation detail, readable from code)
- Cross-filter 200ms debounce (covered by existing fetchAllViews fan-out patterns)
- `primaryPackages` → `packages` naming (one-off TS interface detail)

## Follow-up Work

- `acquire_heavy_query_slot` still not wired for reject-history workers (pre-existing gap; tracked in
  service-patterns.md §RQ Worker Concurrency Gate).

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/` and active project guidance.
