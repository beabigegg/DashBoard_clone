---
change-id: prod-history-query-mode-tabs
schema-version: 0.1.0
last-changed: 2026-05-14
risk: medium
tier: 2
---

# Test Plan: prod-history-query-mode-tabs

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 | e2e | frontend/tests/playwright/production-history-query-mode-tabs.spec.ts | 1 |
| AC-2 | unit | frontend/tests/validation/useProductionHistory.validation.test.js | 0 |
| AC-2 | e2e | frontend/tests/playwright/production-history-query-mode-tabs.spec.ts | 1 |
| AC-3 | unit | frontend/tests/validation/useProductionHistory.validation.test.js | 0 |
| AC-3 | e2e | frontend/tests/playwright/production-history-query-mode-tabs.spec.ts | 1 |
| AC-4 | unit | tests/test_production_history_routes.py | 0 |
| AC-4 | contract | tests/test_api_contract.py | 1 |
| AC-4 | integration | tests/test_production_history_routes.py | 1 |
| AC-5 | integration | tests/test_production_history_service.py | 1 |
| AC-5 | (review) | specs/changes/prod-history-query-mode-tabs/proposal.md | n/a |
| AC-6 | unit | frontend/tests/validation/useProductionHistory.validation.test.js | 0 |
| AC-6 | e2e | frontend/tests/playwright/production-history-query-mode-tabs.spec.ts | 1 |
| AC-7 | unit | tests/test_production_history_service.py | 0 |
| AC-7 | contract | tests/test_api_contract.py | 1 |
| AC-7 | integration | tests/test_production_history_routes.py | 1 |
| AC-8 | unit | frontend/tests/validation/useProductionHistory.validation.test.js | 0 |

## Test Families Required

unit, contract, integration, e2e, data-boundary

Per-family detail (test names, one line each):

**unit — backend** `tests/test_production_history_service.py` (extend; new class `TestValidateQueryParamsModeSplit`)
- `test_identifier_mode_no_dates_accepted` — wildcard tokens present, dates omitted → no raise
- `test_identifier_mode_runs_wide_window` — no-date identifier query produces wide/all-time bind, not 30-day default
- `test_classification_mode_missing_dates_still_raises` — pj_types present, no dates → dates-required error (PHF-08)
- `test_classification_mode_unchanged_with_dates` — AC-7 backward compat (existing type+date flow byte-identical bind)
- `test_identifier_mode_with_dates_still_honors_them` — dates supplied alongside tokens → date predicate kept

**unit — frontend** `frontend/tests/validation/useProductionHistory.validation.test.js` (extend)
- `Tab A submit blocked when pj_types empty` / `... when start_date|end_date empty`
- `Tab B submit allowed with only wildcard tokens, no TYPE, no dates`
- `Tab B payload omits start_date/end_date when no dates set`
- `clearAll resets first-tier selections, 3 wildcard textareas, date range to 30-day default, supplementary/matrix filter, results`
- `i18n: tab labels / 清除篩選 / mode validation messages present in every locale bundle` (AC-8)

**contract** `tests/test_api_contract.py` (extend)
- `test_query_payload_dates_optional_with_identifier_tokens` — accepts payload, omitted dates + tokens (api-contract 1.4.0)
- `test_query_payload_classification_mode_still_requires_dates` — rejects pj_types-only payload missing dates

**integration — backend route** `tests/test_production_history_routes.py` (extend)
- `test_query_identifier_only_no_dates_returns_results` — route returns success envelope, no dates
- `test_query_classification_only_no_dates_returns_validation_error` — route returns validation error envelope
- `test_query_identifier_wide_window_bounded` — AC-5: route-level assert the all-time path applies the agreed wide cap / chunk bound (no unbounded scan)

**data-boundary** covered by extending integration assertions in `tests/test_production_history_routes.py` — confirm wide/all-time identifier result rows match existing data-shape-contract row shape (no new family file).

**e2e** `frontend/tests/playwright/production-history-query-mode-tabs.spec.ts` (new spec)
- `tabs render and switch between 依產品分類查詢 and 依識別碼查詢`
- `Tab A blocks query with empty TYPE/dates showing validation message`
- `Tab B has no date row; paste LOT ID and query succeeds without TYPE/dates`
- `清除篩選 returns page to initial empty state across both tabs`

## Out of Scope

- Cached cross-filter mechanism, wildcard grammar/parsing (`parse_wildcard_tokens`) — non-goals; covered by existing `production-history-wildcard-paste.spec.ts` / `cross-filter` suites.
- Second-tier supplementary (WorkCenter/Equipment) and matrix/detail rendering logic.
- resilience, monkey, soak — no new failure surface introduced.

## Notes

- **Stress decision**: NO new scenario in `tests/stress/test_production_history_stress.py`. AC-5 (identifier no-date unbounded-scan risk) is an *architecture* decision recorded in proposal.md (wide cap vs. unbounded) and verified by a deterministic Tier-1 integration assertion (`test_query_identifier_wide_window_bounded`) — stress tests measure concurrency/latency thresholds, not query-plan boundedness, and would not detect an unbounded scan reliably. Existing concurrent-query stress coverage already exercises the endpoint; the new mode adds no concurrency dimension.
- New e2e spec rather than extending an existing one — the two-tab flow is a distinct page-shell concern; existing `production-history-*.spec.ts` files are scoped to single-feature flows.
- All other backend/frontend coverage extends existing files; only one new file (the e2e spec).
- Tests must fail before implementation: mode-split validate tests, contract optional-date tests, and the new e2e spec.
