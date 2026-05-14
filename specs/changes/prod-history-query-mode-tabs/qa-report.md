# QA Report — prod-history-query-mode-tabs

## Gate Results

| gate | command | result |
|---|---|---|
| backend unit/contract/integration | `pytest tests/test_production_history_{service,routes,sql_runtime}.py tests/test_api_contract.py` | PASS — 102 passed in 33.04s |
| frontend unit (vitest) | `npm run test` | PASS — 30 files, 331 tests |
| frontend validation file | `vitest run tests/validation/useProductionHistory.validation.test.js` | PASS — 45/45 |
| frontend legacy | `npm run test:legacy` | PASS — 251/251 |
| type-check | `npm run type-check` (vue-tsc --noEmit) | PASS — clean |
| css-governance | `npm run css:check` | PASS — 0 errors, 47 pre-existing warnings (none in production-history/) |
| contract-validate | `cdd-kit validate --contracts` | PASS — all validations passed |
| playwright | (deferred to CI `e2e-critical`) | NOT RUN LOCALLY — spec inspected statically |

## Acceptance-Criteria Verification

| AC | status | evidence |
|---|---|---|
| AC-1 two switchable query-mode tabs | covered | E2E `tabs render and switch between 依產品分類查詢 and 依識別碼查詢 (AC-1)` asserts default Tab A active, panel visibility toggles, switch back. App.vue tablist/tab/tabpanel roles (ui-ux H1 applied). |
| AC-2 Tab A blocks empty TYPE/dates with message | covered | E2E `Tab A blocks query with empty TYPE…` asserts `ph-form-error` visible + `queryRequests.length === 0`. Unit cases in useProductionHistory.validation.test.js (Tab A submit-blocked). Backend `test_classification_mode_missing_dates_still_raises` / `test_classification_mode_missing_pj_types_still_raises`. |
| AC-3 Tab B no date row, query without TYPE/dates | covered | E2E `Tab B has no date row; paste LOT ID…` asserts date inputs hidden, payload `start_date/end_date/pj_types` all `undefined`, query succeeds. Backend `test_identifier_mode_no_dates_accepted`. |
| AC-4 validate_query_params mode-aware | covered | Verified in source `production_history_service.py:86-176` — `is_identifier_mode` gate, dates optional + pj_types optional in identifier mode, dates-required raise retained for classification. Backend `TestValidateQueryParamsModeSplit` (8 cases), route `TestQueryModeSplitRoutes` (3), contract `TestProductionHistoryQueryModeContract` (2). business PHF-07/PHF-08. |
| AC-5 no-date path bounded, no unbounded scan | covered | Option B (730-day wide window anchored at today) in source `:155-162`. `test_query_identifier_wide_window_bounded` (service + route level) asserts chunk span == MAX_DATE_RANGE_DAYS and chunk_start ≥ today−730d. Decision recorded in proposal.md §Key Decisions; deterministic, no Oracle-optimizer reliance. |
| AC-6 清除篩選 button resets all state | covered | E2E `清除篩選 returns page to initial empty state` asserts textarea cleared + empty-state restored after a query. Unit `clearAll resets…` in validation test. App.vue wires useFirstTierFilters.clearAll + resetResults. |
| AC-7 existing date-bearing callers unchanged | covered | See regression-report.md. `test_classification_mode_unchanged_with_dates` (byte-identical bind), pre-existing tests `test_validate_query_params_missing_pj_types/_missing_dates/_max_date_range/_730d_boundary` all still pass within the 102-green sweep. |
| AC-8 new user-visible text synced across locales | covered (vacuously) | `frontend/src/production-history/` has NO i18n layer — all strings hard-coded zh-TW (consistent with the existing module). New strings added in the same single-language style; no partial-locale state possible. AC-8 satisfied by absence of a multi-locale system. |

## Test-Evidence Summary

- Backend: 13 new tests (8 service `TestValidateQueryParamsModeSplit`, 3 route `TestQueryModeSplitRoutes`, 2 contract `TestProductionHistoryQueryModeContract`). Full backend sweep 102 passed.
- Frontend: useProductionHistory.validation.test.js 45/45 (+24 new); full vitest 331/331; legacy 251/251; type-check clean; build PASS; css:check 0 errors.
- E2E: 1 new spec `production-history-query-mode-tabs.spec.ts` (4 tests) covering AC-1/2/3/6 with payload-level assertions; 4 prior specs reconciled to the tab split. Playwright NOT executed locally — deferred to CI `playwright-critical-journeys`; specs inspected statically and well-formed.
- Contracts: api 1.3.0→1.4.0, api-inventory 1.1.3→1.1.4, business 1.3.0→1.4.0 (PHF-07/PHF-08 + 2 decision-table rows). `cdd-kit validate --contracts` PASS.
- Reviews: ui-ux-reviewer approved-with-changes (H1/H2/M2/M3/M4/L5 all applied); visual-reviewer approved-with-changes (SF-1/SF-2 applied).

## Pre-existing Failures Excluded From This Gate

None. No failing tests observed in any locally-run gate.

## Risks / Residual Gaps

- **proposal.md open risk — FIRSTNAME (wafer_lots) index coverage unconfirmed.** A wafer-lot-only no-date query relies on `FIRSTNAME` to bound the 730-day scan. If unindexed, the scan is wide but still date-bounded (not full-table) — low severity. Owner: backend-engineer. Not a blocker; revisit if production Oracle load on wafer-lot lookups is observed high.
- **Spool reuse drift (accepted).** Wide-window `start_date` shifts daily → different `dataset_id` across calendar days for the same no-date identifier query. Accepted in proposal.md — production-history is on-demand-only, intra-day reuse still works.
- **Playwright not executed locally.** 4 new + 4 reconciled specs verified by static inspection only. CI `playwright-critical-journeys` MUST run green before merge.

## Fixback Routing

None — no failures.

## Decision

approved-with-conditions

Conditions (all CI-gate, no code changes required):
1. CI `playwright-critical-journeys` runs green — new spec + 4 reconciled specs (not executed locally).
2. CI `unit-mock-integration` and `frontend-unit` gates green on the PR commit (locally verified, must be confirmed in CI per ci-gates.md).
