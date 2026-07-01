---
change-id: yield-alert-kpi-csv-parity
schema-version: 0.1.0
last-changed: 2026-07-01
---

# Implementation Plan: yield-alert-kpi-csv-parity

## Objective

Make the yield-alert-center KPI summary cards (`移轉量`/`報廢量`) reconcile with the
detail-list CSV export under the same filters, and remove DuckDB float-noise from
the CSV numeric columns. Concretely:

1. Rescope the top-level KPI summary (`_query_summary` in
   `yield_alert_sql_runtime.py`) to the SAME alert-candidate row set as
   `_query_alerts()` by factoring the shared CTE chain into one builder
   (design.md Decision 1), computing `transaction_qty` as a SUM over DISTINCT
   `tx_extra_cols` (+ bucketed `DATE_BUCKET`) and `scrap_qty` as a plain SUM
   (design.md Decision 2, YA-13).
2. Thread `risk_threshold`/`min_scrap_qty` from `try_compute_view_from_spool`
   into the rescoped summary, and fix `api_yield_alert_summary` (the `/summary`
   route) to forward those two params (today dropped → defaults) so `/view` and
   `/summary` return identical KPI numbers.
3. Round `toPcs(transaction_qty)` / `toPcs(scrap_qty)` via `Math.round` in
   `_buildAlertsCSV()` (design.md Decision 4, data-shape §3.16.7).

The `GET /api/yield-alert/view` and `/summary` response *shapes* stay unchanged;
only summary numeric values/semantics change.

## Execution Scope

### In Scope
- Factor the `_query_alerts()` CTE chain (`_tx_daily → tx_lookup → alert_groups →
  alert_with_tx → alerts_computed → alerts_filtered`) into a shared builder reused
  by both `_query_alerts()` and the rescoped `_query_summary()`
  (`src/mes_dashboard/services/yield_alert_sql_runtime.py`).
- Rescope `_query_summary()` (or its replacement) to accept `risk_threshold` /
  `min_scrap_qty` and compute KPI totals from `alerts_filtered`.
- Wire `risk_threshold` / `min_scrap_qty` from `try_compute_view_from_spool` into
  the summary call (currently only forwarded to `_query_alerts`).
- Fix `api_yield_alert_summary` route to forward `risk_threshold` / `min_scrap_qty`
  into `apply_cached_view` (`src/mes_dashboard/routes/yield_alert_routes.py`).
- Round CSV `transaction_qty` / `scrap_qty` columns via `Math.round`
  (`frontend/src/yield-alert-center/App.vue` `_buildAlertsCSV`).
- Regenerate contract samples `tests/contract/samples/get_yield_alert_view.json`
  and `get_yield_alert_summary.json` (value drift only, no shape drift).
- Write/run the backend, frontend, contract, and integration tests assigned in
  test-plan.md.

### Out of Scope
- `_query_trend`, `_query_heatmap`, `_query_station_summary`,
  `_query_package_summary` — these keep their current broader (non-threshold)
  scope. Do NOT rescope them (design.md Decision 3 / YA-13 scope boundary).
- `contracts/api/api-contract.md` — deliberately deferred (hook-blocked, user
  declined bypass; see change-classification.md "Clarifications or Assumptions").
  Do NOT edit it. YA-13 + §3.16.7 already document the value-semantics change.
- `query_alert_candidates()` legacy pandas path in `yield_alert_service.py` — a
  separate pre-DuckDB code path, not touched by this change.
- Any signature change to `apply_view` / `apply_cached_view` in
  `yield_alert_dataset_cache.py` — CONFIRMED it already threads both params (see
  Known Risks #1). No change there.
- Schema/spool/data migration, cache purge, env vars, CSS/UI, new CI workflows.
- E2E Playwright CSV spec — optional at Tier 2, not authored/blocking here.

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | reproduction (backend) | Write failing test proving `_query_summary` returns whole-scope totals (omits alert-candidate predicate) instead of alert-candidate totals, AND a failing data-boundary test proving a naive `SUM(transaction_qty)` over multi-reason_code `alerts_filtered`-shaped rows double-counts vs the `tx_extra_cols` deduped total. Must FAIL against current code. | bug-fix-engineer |
| IP-2 | reproduction (frontend) | Write failing test proving `_buildAlertsCSV()` emits raw float noise (e.g. `4011.9999999999995`) for `transaction_qty`/`scrap_qty` via `String(v)`. Must FAIL against current code. | bug-fix-engineer |
| IP-3 | SQL/service (backend) | Factor the `_query_alerts` CTE chain into a shared builder; implement rescoped `_query_summary` reading `alerts_filtered` (design.md Decisions 1+2). `transaction_qty` = SUM over DISTINCT (`WORKORDER`, `DEPARTMENT_GROUP`, `PROCESS_CATEGORY`, `LINE_NAME`, `PACKAGE_NAME`, `TYPE_NAME`, `FUNCTION_NAME`, `OPERATION_TEXT`, bucketed `DATE_BUCKET`); `scrap_qty` = plain SUM. Make IP-1 tests pass. | backend-engineer |
| IP-4 | wiring (backend) | Pass `risk_threshold`/`min_scrap_qty` from `try_compute_view_from_spool` into `_query_summary` (`yield_alert_sql_runtime.py` ~901-907). | backend-engineer |
| IP-5 | route wiring (backend) | Forward `risk_threshold`/`min_scrap_qty` from `api_yield_alert_summary` into `apply_cached_view` (`yield_alert_routes.py` ~430-434); parse them from `request.args` as `/view` does (~352-356). | backend-engineer |
| IP-6 | contract samples (backend) | Regenerate `tests/contract/samples/get_yield_alert_view.json` and `get_yield_alert_summary.json`; confirm value-only drift, no shape drift (AC-7). | backend-engineer |
| IP-7 | CSV formatting (frontend) | Wrap `toPcs(r.transaction_qty)` and `toPcs(r.scrap_qty)` in `Math.round(...)` in `_buildAlertsCSV()` (App.vue ~653-654). Leave `yield_pct`/`risk_score` `.toFixed()` unchanged. Make IP-2 test pass. | frontend-engineer |

## Source Artifact Pointers

| source | relevant pointer | used for |
|---|---|---|
| design.md | Decision 1 (shared CTE builder, option b) | IP-3 implementation constraint |
| design.md | Decision 2 (dedup key = `tx_extra_cols`, NOT `_TX_DEDUP_COLS`) | IP-3 dedup dimension |
| design.md | Decision 3 (KPI-summary-only scope) | Out-of-scope boundary |
| design.md | Decision 4 (`Math.round` to whole pcs) | IP-7 formatting rule |
| design.md | Open Risk #2 (/summary drops threshold params) | IP-5 required (not optional) |
| contracts/business/business-rules.md | YA-13 | authoritative KPI-scope + dedup rule for IP-3/IP-4/IP-5 |
| contracts/data/data-shape-contract.md | §3.16.7 column table | authoritative CSV rounding rule for IP-7 |
| test-plan.md | AC→Test Mapping table | test files to write/run per AC |
| test-plan.md | Notes (real DuckDB, no mocked SQL; per-kwarg assertions) | test convention constraints |
| ci-gates.md | Required Gates table | verification commands / gate names |
| change-classification.md | Clarifications (api-contract.md deferred) | do not touch api-contract.md |

## File-Level Plan

Order: bug-fix-engineer FIRST (reproduce), then backend-engineer + frontend-engineer
implement in their own stacks against the failing tests.

| path or glob | action | owner | notes |
|---|---|---|---|
| tests/test_yield_alert_sql_runtime.py | add failing tests | bug-fix-engineer | IP-1: whole-scope-vs-candidate divergence + naive-sum double-count trap (real DuckDB over parquet fixture, `TestCrossFilterOptions` convention) |
| frontend/tests/yield-alert/App.csv-export.test.js | create + failing test | bug-fix-engineer | IP-2: float-residue reproduction. New file in existing `frontend/tests/yield-alert/` dir |
| src/mes_dashboard/services/yield_alert_sql_runtime.py | edit | backend-engineer | IP-3/IP-4. Shared CTE builder from `_query_alerts` (491-612); rescope `_query_summary` (196-240); wire params in `try_compute_view_from_spool` (901-907). Dedup key = `tx_extra_cols` (534-538) + bucketed `DATE_BUCKET`, NOT `_TX_DEDUP_COLS` (35-39). Preserve `_query_alerts` param order (`all_cte_params = full_params + combined_params`, then `threshold_params`, see 615-623) |
| src/mes_dashboard/routes/yield_alert_routes.py | edit | backend-engineer | IP-5. `api_yield_alert_summary` (402-440): parse + forward `risk_threshold`/`min_scrap_qty`. Mirror `api_yield_alert_view` parsing (352-356) |
| tests/contract/samples/get_yield_alert_view.json | regenerate | backend-engineer | IP-6 (AC-7). Value drift only |
| tests/contract/samples/get_yield_alert_summary.json | regenerate | backend-engineer | IP-6 (AC-7). Value drift only |
| tests/test_yield_alert_sql_runtime.py | add passing tests | backend-engineer | AC-1/AC-3/AC-4 + shared-CTE structural guard (see Test Execution Plan) |
| tests/test_yield_alert_routes.py | add tests | backend-engineer | AC-3 per-kwarg forwarding; AC-7 shape-unchanged (mock `apply_cached_view` per convention) |
| tests/test_yield_alert_service.py | add tests | backend-engineer | AC-1/AC-4 end-to-end reconciliation over real spool parquet |
| tests/test_yield_alert_contracts.py | add tests | backend-engineer | AC-6 YA-13 text + CHANGELOG entries (see Known Risks #2) |
| frontend/src/yield-alert-center/App.vue | edit | frontend-engineer | IP-7. `_buildAlertsCSV` lines 653-654 only |
| frontend/tests/yield-alert/App.csv-export.test.js | complete tests | frontend-engineer | AC-5 rounding + float-residue-fixed cases |

## Contract Updates

All contract writes are ALREADY APPLIED (by spec-architect / contract-reviewer).
Implementation agents must NOT re-author these; only regenerate the machine samples.

- API: DEFERRED — `contracts/api/api-contract.md` intentionally not edited
  (hook-blocked; see change-classification.md Clarifications). Do NOT touch.
- CSS/UI: none.
- Env: none.
- Data shape: `contracts/data/data-shape-contract.md` §3.16.7 — already written
  (CSV rounded-pcs formatting). CHANGELOG `data 1.33.0` present.
- Business logic: `contracts/business/business-rules.md` YA-13 — already written.
  CHANGELOG `business 1.40.0` present.
- CI/CD: none.

## Test Execution Plan

Reference: test-plan.md "Acceptance Criteria → Test Mapping" (authoritative test
IDs/paths). Required phase floor for both backend and frontend engineers before
qa-reviewer: `cdd-kit test select` → `cdd-kit test run --phase collect`,
`--phase targeted`, `--phase changed-area` (evidence in `test-evidence.yml`).
Do NOT put `cdd-kit test run ...` lines in the table below; the selector reads a
bare target or a pytest command.

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 | tests/test_yield_alert_sql_runtime.py::TestQuerySummaryAlertScopeParity::test_transaction_qty_matches_tx_extra_cols_dedup_sum_of_alert_candidates | KPI tx = tx_extra_cols-deduped sum of alert candidates |
| AC-2 | tests/test_yield_alert_sql_runtime.py::TestQuerySummaryAlertScopeParity::test_scrap_qty_matches_sum_of_alert_candidate_rows | KPI scrap = plain SUM of alert-candidate rows |
| AC-3 | tests/test_yield_alert_sql_runtime.py::TestQuerySummaryAlertScopeParity::test_summary_excludes_rows_failing_alert_candidate_predicate | summary drops rows failing `SCRAP_QTY<>0` / threshold exclusion |
| AC-3 | tests/test_yield_alert_routes.py::test_summary_route_forwards_risk_threshold_and_min_scrap_qty | route forwards both params (assert `call_args.kwargs[...]`, not whitelist) |
| AC-3 | tests/test_yield_alert_sql_runtime.py::TestQuerySummaryAlertScopeParity::test_try_compute_view_forwards_risk_threshold_and_min_scrap_qty_to_summary | orchestrator forwards both params to summary |
| AC-4 | tests/test_yield_alert_sql_runtime.py::TestQuerySummaryAlertScopeParity::test_multi_reason_code_group_counts_transaction_qty_once | multi-reason group counted once |
| AC-4 | tests/test_yield_alert_sql_runtime.py::TestQuerySummaryAlertScopeParity::test_department_name_split_within_one_tx_lookup_group_does_not_break_dedup | `_TX_DEDUP_COLS` would be wrong (over-fine) key |
| AC-4 | tests/test_yield_alert_sql_runtime.py::TestQuerySummaryAlertScopeParity::test_naive_sum_over_reason_coded_rows_would_double_count_documents_the_trap | naive-sum trap tripwire |
| AC-5 | frontend/tests/yield-alert/App.csv-export.test.js::builds_alerts_csv_rounds_transaction_qty_and_scrap_qty_to_whole_pcs | CSV cells are whole-pcs integers |
| AC-5 | frontend/tests/yield-alert/App.csv-export.test.js::builds_alerts_csv_reproduces_and_fixes_duckdb_float_residue_case | `4011.99...95` → `4012` |
| AC-6 | tests/test_yield_alert_contracts.py::TestBusinessRuleYA13::test_ya13_rule_documents_kpi_scope_and_tx_extra_cols_dedup_dimension | YA-13 text present + correct dedup key |
| AC-6 | tests/test_yield_alert_contracts.py::TestBusinessRuleYA13::test_changelog_has_version_entries_for_business_data_api | CHANGELOG entries present (see Known Risks #2 re: api entry) |
| AC-7 | tests/contract/samples/get_yield_alert_view.json, get_yield_alert_summary.json (via tests/contract/test_capture_samples.py) | sample regen: value drift only, no shape drift |
| AC-7 | tests/test_yield_alert_routes.py::test_view_and_summary_response_shape_unchanged_after_scope_unification | response shape unchanged |
| AC-1/AC-4 | tests/test_yield_alert_service.py::TestKpiCsvReconciliation::test_summary_and_alerts_reconcile_end_to_end_with_multi_reason_group | KPI↔CSV reconcile end-to-end |
| Decision 1 | tests/test_yield_alert_sql_runtime.py::TestQuerySummaryAlertScopeParity::test_summary_and_alerts_share_the_same_cte_builder | summary + alerts share one CTE builder structurally |

Gate commands (ci-gates.md Required Gates): `ruff check .`; `npm run type-check`;
`pytest tests/test_yield_alert_sql_runtime.py tests/test_yield_alert_service.py
tests/test_yield_alert_routes.py -v`; `npm run test`; `pytest
tests/test_yield_alert_contracts.py` + `cdd-kit validate --contracts`; data-boundary
`pytest tests/test_yield_alert_sql_runtime.py -k "double_count or
department_name_split or naive_sum"`; then `cdd-kit gate yield-alert-kpi-csv-parity`.

## Handoff Constraints

- Lane routing (lane: bug-fix): **bug-fix-engineer runs FIRST** — it diagnoses +
  reproduces (IP-1, IP-2: writes the failing backend and frontend tests) and does
  NOT implement the fix across both stacks. It then hands off to **backend-engineer**
  (SQL/Python: IP-3/IP-4/IP-5/IP-6) and **frontend-engineer** (CSV: IP-7), each of
  whom implements in their own stack using bug-fix-engineer's failing tests as the
  TDD starting point (failing test first, then implementation).
- Parallel-agent evidence: backend-engineer and frontend-engineer both write
  `test-evidence.yml` via `cdd-kit test run`. Per CLAUDE.md promoted learning, the
  later of the two must re-run collect/targeted/changed-area combining BOTH stacks'
  commands into single phase entries before gate sign-off, or the concurrent writes
  overwrite each other.
- Dedup key is `tx_extra_cols` + bucketed `DATE_BUCKET` (design.md Decision 2 /
  YA-13). Do NOT use `_TX_DEDUP_COLS` (it wrongly adds raw `DEPARTMENT_NAME`) and do
  NOT introduce a third variant.
- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this
  plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report
  `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request
  is approved.

## Known Risks

1. **RESOLVED (design assumption verified):** `apply_view` / `apply_cached_view`
   in `yield_alert_dataset_cache.py` (891-902) ALREADY accept and thread
   `risk_threshold`/`min_scrap_qty` into `try_compute_view_from_spool` (926-937).
   No signature change is needed there — this matches design.md's Affected
   Components table ("no signature change"). backend-engineer's scope is unchanged.
2. **CHANGELOG `api` version entry gap (needs test-strategist / backend-engineer
   attention):** test-plan.md's AC-6 test is named
   `test_changelog_has_version_entries_for_business_data_api`, implying it asserts
   business AND data AND api entries. But `contracts/CHANGELOG.md` currently has
   only `business 1.40.0` and `data 1.33.0` — there is intentionally NO `api` entry
   (api-contract.md was deferred per change-classification.md Clarifications). If the
   test literally requires an `api` entry it will fail while the contract is
   correctly deferred. Reconcile: the test must assert only business+data (rename or
   adjust its expectation), OR document the deferred-api decision. This is a
   test-authoring detail owned by backend-engineer/test-strategist; flagged here so
   it is not silently missed. Do NOT resolve it by adding an api-contract.md entry
   (that path is hook-blocked and user-declined).
3. Contract samples (`get_yield_alert_view.json`, `get_yield_alert_summary.json`)
   will regenerate with new summary values; verify only value drift, no shape drift.
   Do not regenerate the OpenAPI exports — no schema change.
4. Full `pytest tests/` re-runs `tests/contract/test_capture_samples.py` and
   regenerates ALL ~160 samples with live values (CLAUDE.md learning). After a full
   run, `git checkout tests/contract/samples/` to revert unrelated churn, then
   re-stage only the two yield-alert samples this change altered.
5. `.cdd/code-map.yml` shows modified/uncommitted in git status; all line ranges in
   this plan were verified by direct source reads, not the map alone.
