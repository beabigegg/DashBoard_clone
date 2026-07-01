---
change-id: yield-alert-kpi-csv-parity
schema-version: 0.1.0
last-changed: 2026-07-01
risk: medium
tier: 2
---

# Test Plan: yield-alert-kpi-csv-parity

## Acceptance Criteria → Test Mapping

Dedup key per design.md Decision 2: `tx_extra_cols` (`WORKORDER`, `DEPARTMENT_GROUP`,
`PROCESS_CATEGORY`, `LINE_NAME`, `PACKAGE_NAME`, `TYPE_NAME`, `FUNCTION_NAME`,
`OPERATION_TEXT`, bucketed `DATE_BUCKET`) — NOT the module-level `_TX_DEDUP_COLS`
(which wrongly includes raw `DEPARTMENT_NAME`). Tests must assert against this
exact key set, not the module constant.

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 | unit (real DuckDB, parquet fixture) | tests/test_yield_alert_sql_runtime.py::TestQuerySummaryAlertScopeParity::test_transaction_qty_matches_tx_extra_cols_dedup_sum_of_alert_candidates | 1 |
| AC-2 | unit (real DuckDB, parquet fixture) | tests/test_yield_alert_sql_runtime.py::TestQuerySummaryAlertScopeParity::test_scrap_qty_matches_sum_of_alert_candidate_rows | 1 |
| AC-3 | unit (real DuckDB, parquet fixture) | tests/test_yield_alert_sql_runtime.py::TestQuerySummaryAlertScopeParity::test_summary_excludes_rows_failing_alert_candidate_predicate | 1 |
| AC-3 | unit (per-kwarg forwarding, route) | tests/test_yield_alert_routes.py::test_summary_route_forwards_risk_threshold_and_min_scrap_qty | 0 |
| AC-3 | unit (per-kwarg forwarding, sql_runtime) | tests/test_yield_alert_sql_runtime.py::TestQuerySummaryAlertScopeParity::test_try_compute_view_forwards_risk_threshold_and_min_scrap_qty_to_summary | 0 |
| AC-4 | unit (real DuckDB, multi-reason fixture) | tests/test_yield_alert_sql_runtime.py::TestQuerySummaryAlertScopeParity::test_multi_reason_code_group_counts_transaction_qty_once | 1 |
| AC-4 | unit (dedup-key regression tripwire) | tests/test_yield_alert_sql_runtime.py::TestQuerySummaryAlertScopeParity::test_department_name_split_within_one_tx_lookup_group_does_not_break_dedup | 1 |
| AC-4 | data-boundary (naive-sum regression tripwire) | tests/test_yield_alert_sql_runtime.py::TestQuerySummaryAlertScopeParity::test_naive_sum_over_reason_coded_rows_would_double_count_documents_the_trap | 1 |
| AC-5 | unit (frontend CSV formatting) | frontend/tests/yield-alert/App.csv-export.test.js::builds_alerts_csv_rounds_transaction_qty_and_scrap_qty_to_whole_pcs | 0 |
| AC-5 | unit (frontend CSV formatting) | frontend/tests/yield-alert/App.csv-export.test.js::builds_alerts_csv_reproduces_and_fixes_duckdb_float_residue_case | 0 |
| AC-6 | contract | tests/test_yield_alert_contracts.py::TestBusinessRuleYA13::test_ya13_rule_documents_kpi_scope_and_tx_extra_cols_dedup_dimension | 0 |
| AC-6 | contract (CHANGELOG) | tests/test_yield_alert_contracts.py::TestBusinessRuleYA13::test_changelog_has_version_entries_for_business_data_api | 0 |
| AC-7 | contract (sample pin) | tests/contract/samples/get_yield_alert_view.json, get_yield_alert_summary.json (regenerated, diffed via test_capture_samples.py) | 1 |
| AC-7 | integration (route shape) | tests/test_yield_alert_routes.py::test_view_and_summary_response_shape_unchanged_after_scope_unification | 1 |
| AC-1/AC-4 | integration (route→service→sql_runtime, real spool parquet) | tests/test_yield_alert_service.py::TestKpiCsvReconciliation::test_summary_and_alerts_reconcile_end_to_end_with_multi_reason_group | 1 |
| (Decision 1, shared-CTE-by-construction) | unit (regression guard) | tests/test_yield_alert_sql_runtime.py::TestQuerySummaryAlertScopeParity::test_summary_and_alerts_share_the_same_cte_builder | 1 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0-1 | Backend: `_query_summary` scope + tx-dedup against real DuckDB over an in-memory/tmp-path parquet fixture (follow `TestCrossFilterOptions` convention — no mocked SQL). Frontend: CSV row formatting for transaction_qty/scrap_qty. |
| contract | 0-1 | YA-13 business-rule text assertion, CHANGELOG entry, `GET /api/yield-alert/view` sample regenerate with no unexpected field/shape drift. |
| integration | 1 | KPI↔CSV reconciliation across `_query_summary` + `_query_alerts` sharing one spool fixture; route-level response-shape pin. |
| e2e | deferred | Optional per classifier (Tier 2, not blocking). If added: Playwright CSV download + KPI card value cross-check on `yield-alert-center` page; candidate file `frontend/tests/playwright/yield-alert-csv-export.spec.ts` (not required for this change's gate). |
| data-boundary | 1 | (a) SQL: naive `SUM(transaction_qty)` over `alerts_filtered`-shaped rows with a multi-reason-code group must diverge from the deduped total — proves the double-count trap without the fix; (b) SQL: a fixture where one `tx_extra_cols` group spans two `DEPARTMENT_NAME` raw values must still dedup to one `transaction_qty` (proves `_TX_DEDUP_COLS` would be the wrong, over-fine key per design.md Decision 2); (c) CSV: float-residue fixture value (e.g. raw `4.0119999999999996` K-PCS) must render via `Math.round` as a clean whole-pcs integer string in the CSV cell, not `String(v)` of the raw float. |
| resilience | n/a | Not required — no new spool-miss/fallback path introduced by this change. |
| monkey | n/a | Not required. |
| stress / soak | n/a | Not required — no new load/concurrency surface (per change-classification). |

## Out of Scope

- Per design.md Decision 3: trend/heatmap/station_summary/package_summary keep their current (broader, non-threshold) scope — this is an explicit documented non-goal, not a gap. No test in this plan asserts these four functions apply the alert-candidate predicate; a future change would need its own AC set to do so.
- `query_alert_candidates()` (legacy pandas path in `yield_alert_service.py`, covered by `test_yield_alert_service.py` today) is a separate, pre-DuckDB-spool code path; this change scopes only the DuckDB spool runtime (`yield_alert_sql_runtime.py`) per design.md's Affected Components table.
- E2E Playwright coverage is optional at Tier 2 and not a blocking gate for this change; listed above as a deferred candidate only.
- CSV rounding precision below whole-pcs granularity (e.g. sub-pcs display) is out of scope — K-PCS source data is an exact multiple of 0.001, so `Math.round` to whole pcs is lossless (design.md Decision 4); `.toFixed()` parity with yield_pct/risk_score was considered and rejected.

## Notes

Backend dedup/scope tests must exercise the real DuckDB engine over parquet fixtures (per `TestCrossFilterOptions` convention in this file) — do not mock SQL execution, since the bug is in aggregation semantics, not call wiring. Per design.md Decision 1, summary and alerts share one CTE builder by construction; assert this structurally (same SQL fragment or same helper function), not only via output-value equality, so a future edit to one path cannot silently drift from the other. Route-level response-shape tests continue to mock `apply_cached_view`/`try_compute_view_from_spool` per existing convention (AC-7); numeric reconciliation is proven only at the sql_runtime/service integration layer where real aggregation runs. `/summary` route wiring of `risk_threshold`/`min_scrap_qty` (design.md Open Risk #2) is a required regression surface, not optional — assert via `call_args.kwargs[...]`, not `assert_called_once_with()`.
