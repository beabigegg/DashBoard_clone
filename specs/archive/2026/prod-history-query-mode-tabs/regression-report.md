# Regression Report — prod-history-query-mode-tabs

## Scope

Follow-up to shipped change `prod-history-first-tier-cache-filters`. Backward-compat constraint (AC-7): existing callers that always send `start_date`/`end_date` must behave exactly as before.

## AC-7 Backward-Compatibility Assessment — no regression

- **validate_query_params unchanged branch.** Source `production_history_service.py:152-174`: when both `start_raw` and `end_raw` are non-empty, control flows through the original `_parse_date` → start>end check → 730-day span cap — byte-identical to pre-change logic. The new Option B branch (`:155-162`) is reached only when dates are **absent AND** identifier tokens present.
- **Classification-mode validation preserved.** `pj_types` requirement still raised for classification mode (`:149-150`); only mode-gated below token parsing so mode is known first — net behavior for a no-token request is identical.
- **Evidence:** `test_classification_mode_unchanged_with_dates` (byte-identical bind assertion). Pre-existing tests `test_validate_query_params_missing_pj_types`, `test_validate_query_params_missing_dates`, `test_validate_query_params_max_date_range`, `test_730d_boundary_is_valid`, `test_731d_returns_validation_error`, `test_query_missing_pj_types`, `test_query_missing_dates`, `test_query_date_range_exceeded` — all pass within the locally-confirmed 102-green backend sweep.
- API contract change (required → conditionally-optional) is additive; old clients sending dates hit the unchanged path.

## Regression Scope — evidence each area is unaffected

| area | evidence |
|---|---|
| Classification-mode flow | Unchanged validation branch + `test_classification_mode_unchanged_with_dates`; E2E Tab A still default-active and gated on TYPE/dates. |
| Cross-filter cache mechanism (4-tuple DISTINCT + in-memory filter) | Non-goal; no source touched in cache path. `production-history-cross-filter.spec.ts` reconciled with only +10/-1 lines (tab-switch setup). proposal.md confirms no SQL/pipeline change. |
| Wildcard grammar / parsing (`parse_wildcard_tokens`) | Non-goal; `parse_wildcard_tokens` calls unchanged in source. `production-history-wildcard-paste.spec.ts` reconciled (+15/-21, mechanical tab-switch adaptation); parser idempotence still covered at data layer. |
| Second-tier supplementary filters (WorkCenter/Equipment) | Non-goal; not touched. Route tests `test_page_accepts_matrix_filter_fields` / `test_matrix_accepts_same_filter_schema` pass in the 102-green sweep. |
| Matrix/detail rendering | Non-goal; `production_history_sql_runtime.py` unchanged (proposal §Affected Components: "No change — result row shape identical"). sql_runtime tests 25/25 pass. Data-shape contract: no-change. |
| SQL templates / spool parquet | `main_query.sql` / `count_query.sql` untouched — wide window flows through existing binds. No parquet cleanup needed (ci-gates.md Rollback). |

## Reconciled Playwright Specs — intent assessment

- **production-history-cross-filter.spec.ts** (+10/-1), **production-history-wildcard-paste.spec.ts** (+15/-21), **production-history-filter-options-error.spec.ts** (+11/-2): mechanical reconciles — add a tab-switch setup step / update `waitForSelector` anchors to the new `ph-mode-tab-*` testids. Test intent preserved; assertions unchanged.
- **production-history-multi-line-input.spec.ts** (+15/-19): one **deliberate intent change**. The old test `Empty textarea omits the wildcard field entirely (AC-3 back-compat)` asserted payload-shaping for a query submitted from the single-panel form with empty wildcard inputs. After the two-tab split that flow no longer exists by design — wildcard fields live only in Tab B, which requires ≥1 token to submit. The test was rewritten as `Empty identifier query is blocked client-side — no request sent`, asserting a validation message + zero requests.
  - **Assessment: acceptable intent change, not a coverage loss.** The flow being tested was removed by design, not by accident. The underlying wildcard-field-omission / mode-gated payload behavior is still covered at the data layer by `useProductionHistory.validation.test.js` (buildModePayload field-stripping + "Tab B payload omits start_date/end_date" cases). The mixed-separator dedup test in the same file is preserved intact. Net E2E coverage tracks the new design correctly.

## Verdict

no-regression — backward-compat path is structurally unchanged and test-proven; all out-of-scope areas verified untouched; the one reconciled-spec intent change is design-driven with equivalent data-layer coverage. Residual: playwright suite must run green in CI (not executed locally).
