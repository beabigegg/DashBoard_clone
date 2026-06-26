# Archive: rh-remove-supplementary-filter

> **Cold Data Warning**: This archive is historical evidence. Current requirements live in `contracts/` and active project guidance.

## Change Summary

Removed the supplementary (second-layer) DuckDB filter panel from the reject-history `POST /query` primary path and promoted 報廢原因 (LOSSREASONNAME) as a 4th primary prefilter column injected at the Oracle `BASE_WHERE` layer. The supplementary `{{ WHERE_CLAUSE }}` filter section (workcenter_groups, packages, reasons, types) was fully removed from the POST path. The `GET /view` supplementary DuckDB layer was intentionally retained and is out of scope for this change. The monorepo's sole consumer (frontend `reject-history/`) was updated atomically — no deprecation window, following the same precedent as api 1.27.0/1.28.0.

## Final Behavior

- `POST /api/reject-history/query` accepts four primary prefilters: `pj_types[]`, `packages[]`, `pj_functions[]`, `reasons[]` — all injected into `{{ BASE_WHERE }}` of the `reject_raw` CTE (Oracle layer, before GROUP BY).
- `reasons[]` uses `NVL(TRIM(r.LOSSREASONNAME), '(未填寫)') IN (:reason_0, ...)` with alias `r` (table `DWH.DW_MES_LOTREJECTHISTORY r`); sentinel `(未填寫)` is distinct from container-level `(NA)`.
- `workcenter_groups[]` is no longer accepted; sending it is silently ignored (breaking for external callers; sole consumer is monorepo frontend, cut over atomically).
- Frontend: supplementary filter panel markup, props, emits, CSS (`.supplementary-panel`, `.supplementary-header`, `.supplementary-row`, `.supplementary-toolbar`), and DuckDB `buildUserConditions` branch removed. `.primary-prefilter-row` grid changed from `repeat(3)` to `repeat(4)`. `primaryReasons` ref wired through App.vue → FilterPanel with URL state persistence and filter chip via `CommittedPrimary`.

## Final Contracts Updated

| contract | version | evidence |
|---|---|---|
| `contracts/api/api-contract.md` | api 1.29.0 | backend-engineer.yml, contract-reviewer (5.3 done) |
| `contracts/data/data-shape-contract.md` | data 1.26.0 | tasks.yml 2.4 done |
| `contracts/business/business-rules.md` | business 1.31.0 (RHPF-07, RHPF-08) | tasks.yml 2.5 done |
| `contracts/css/css-contract.md` | css 1.10.0 | tasks.yml 2.2 done |
| `contracts/CHANGELOG.md` | all four versions | `cdd-kit validate --versions` pass |
| `contracts/openapi.json` + `contracts/api/openapi.json` | regenerated | `openapi-sync` CI gate pass |

## Final Tests Added / Updated

| file | nature | evidence |
|---|---|---|
| `tests/test_reject_history_service.py` | 8 new: reasons bind/sentinel/empty/single/multi | backend-engineer.yml |
| `tests/test_reject_history_routes.py` | 4 new: forwarding + workcenter_groups absence | backend-engineer.yml |
| `tests/test_reject_dataset_cache.py` | 2 new: cache-key isolation, distinct reasons | backend-engineer.yml |
| `tests/test_reject_query_job_service.py` | 2 new: job service forwarding | backend-engineer.yml |
| `tests/test_reject_history_async_routes.py` | 2 new: async path forwarding + wc_groups absent | backend-engineer.yml |
| `tests/test_reject_history_unified_job.py` | 2 new: unified job reasons plumbing | backend-engineer.yml |
| `frontend/tests/playwright/reject-history-filter.spec.ts` | reasons multiselect + POST body assertions | frontend-engineer.yml |
| `frontend/tests/validation/useRejectHistory.validation.test.js` | reasons in POST body; wc_groups absent; primaryReasons normalization | frontend-engineer.yml |
| `frontend/tests/legacy/reject-history-date-range-limit.test.js` | pin updated 190→365 | CI fix commit 6988392b |
| `frontend/tests/legacy/portal-shell-navigation.test.js` | drawer order assertion [1,2,3,4,6]→[1,2,3,4,5] | CI fix commit 6988392b |

## Final CI/CD Gates

All 7 required gates passed on GitHub Actions (run 28207636556/28207636602):
`contract-and-fast-tests`, `unit-and-integration-tests`, `frontend-unit-tests`, `openapi-sync`, `released-pages-hardening`, `real-infra-smoke`, `e2e-critical`.

## Production Reality Findings

1. **BLK-1 (`:loading` missing)**: FilterPanel 報廢原因 MultiSelect was missing `:loading="primaryPrefilterLoading"`. Fixed during UI/UX review.
2. **BLK-2 (URL state not persisted)**: `primaryReasons` missing from `updateUrlState()` / `restoreFromUrl()`. Fixed during UI/UX review.
3. **BLK-3 (no filter chip)**: No visibility of committed reason prefilter after query. Fixed by adding `reasons: string[]` to `CommittedPrimary` and snapshotting at query submission.
4. **Dead `workcenterGroups` in ComputeViewParams**: Still referenced in `useRejectHistoryDuckDB.ts` after frontend pass. Removed.
5. **Pre-existing CI gap (contract-driven-gates.yml)**: `cdd-kit validate --contracts` step was missing — exposed by cdd-kit 3.5.0 refresh. Fixed by adding `pip install jsonschema` + validate step to the CI workflow.
6. **Legacy test pin drift (two tests)**: The visual polish commit (`af7f424b`) bumped `PRIMARY_QUERY_MAX_DAYS` 190→365 without updating the legacy test pin. The cdd-kit refresh commit (`6ce0ce6a`) swapped eap-analysis/dev-tools drawer order without updating the nav tree test assertion. Both fixed in commit 6988392b.

## Lessons Promoted to Standards

| lesson | classification | target | evidence |
|---|---|---|---|
| Legacy test pin drift: when changing a module-level constant or manifest-derived structure, grep `tests/legacy/` for the old value and update all pin assertions in the same commit | promote-to-guidance | `docs/architecture/test-discipline.md` §Legacy Test Suite — Constant Pin Drift | archive.md §Finding #6; commit 6988392b |
| `_build_base_where` vs `_build_where_clause` scope boundary | rejected (service-specific, no cross-service recurrence; state is transient pending follow-up cleanup) | — | backend-engineer.yml IP-2 note |

## Follow-up Work

- `rh-primary-prefilter` close (`/cdd-close rh-primary-prefilter`) still pending.
- `_build_where_clause` workcenter_groups/reasons/packages/types branches in the GET `/view` supplementary layer are now dead code from the frontend's perspective (frontend no longer sends these). Removing them is a separate tracked change.
