---
change-id: yield-alert-spool-refactor
schema-version: 0.1.0
last-changed: 2026-06-16
---

# Implementation Plan: yield-alert-spool-refactor

## Objective
Collapse all four yield-alert views (trend, Summary cards, heatmap, alert list) onto a single `yield_alert_dataset` DuckDB spool built from `ERP_WIP_MOVETXN_DETAIL`; add a `process_type` (GA%/GC%) selector; add `SOURCE_CODE` (LOT) + `REJECT_LINKED` columns; retire the live Oracle trend/summary path and the separate reject-linkage round-trip. See design.md §Summary, §Key Decisions D1–D5.

## Execution Scope

### In Scope
- backend-engineer: spool builder, service orchestration, route validation, SQL, namespace confirm, backend tests (Backend Steps B1–B8).
- frontend-engineer: process_type selector, LOT column, new spool row shape in DuckDB compute, additive orchestrator change, frontend tests (Frontend Steps F1–F6).

### Out of Scope
- Other report pages (WIP, Hold, reject-history, resource-history) — test-plan.md §Out of Scope.
- Yield formula change (`SCRAP_QTY / TRANSACTION_QTY`) — change-request §Non-goals; YA-04.
- New CSS rules / new env var (css + env contracts confirm-only) — change-classification §Required Contracts.
- stress/soak/visual/qa evidence (owned by stress-soak-engineer, visual-reviewer, qa-reviewer).

## Non-goals
- Do NOT mint a new spool namespace — reuse `yield_alert_dataset` (D1).
- Do NOT re-introduce a live Oracle trend/summary fallback (D2 / Alt-A).
- Do NOT modify `MultiSelect.vue` (shared by 12 apps; use, don't edit).
- Do NOT make `useFilterOrchestrator.ts` change anything other than additive.
- Do NOT change alert-trigger thresholds or workorder yield granularity (YA-05).
- Do NOT coerce an invalid `process_type` to GA% — reject it (D5 / YA-01).

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | spool builder | bump `_SCHEMA_VERSION` 4→5; fold process_type into query-id hash | backend-engineer |
| IP-2 | spool SQL/builder | MOVETXN→MOVETXN_DETAIL; process_type scope; SOURCE_CODE; REJECT_LINKED join; drop PACKAGE filter | backend-engineer |
| IP-3 | service | retire live trend/summary Oracle path + separate reject-linkage round-trip | backend-engineer |
| IP-4 | route | validate process_type (default GA%, invalid→VALIDATION_ERROR); thread source_code | backend-engineer |
| IP-5 | contracts | regen openapi.json + recapture response sample | backend-engineer |
| IP-6 | frontend | process_type selector, LOT column, new spool shape, additive orchestrator | frontend-engineer |

## Source Artifact Pointers

| source | relevant pointer | used for |
|---|---|---|
| design.md | §Key Decisions D1–D5; §Migration/Rollback | implementation constraints |
| test-plan.md | AC-1..AC-8 map; §Test File Index; §Test Update Contract | tests to write/update/delete |
| ci-gates.md | §Required Gates; §Promotion/Rollback Policy | verification commands |
| business-rules.md | YA-01..YA-09 | scope/invariant rules |
| data-shape-contract.md | §3.16 (3.16.1–3.16.4) | spool column schema + invariants |
| api-contract.md | yield-alert query/alerts entries | request param + response field |

## File-Level Plan

| path or glob | action | notes |
|---|---|---|
| `src/mes_dashboard/services/yield_alert_dataset_cache.py` | edit | bump `_SCHEMA_VERSION` 4→5; `_load_primary_detail_df` (L402-441) + `execute_primary_query` (L457-639) gain `process_type`; `_make_query_id` (L153) folds process_type; `_DETAIL_COLUMNS` += SOURCE_CODE, REJECT_LINKED; reject join replaces `execute_linkage_query`/`_enrich_alerts_with_linkage`; `apply_view` (L905) SELECT/GROUP BY += SOURCE_CODE |
| `src/mes_dashboard/services/yield_alert_service.py` | edit | retire live `query_yield_trend`/`query_yield_summary` Oracle path; remove `_compute_reject_linkage` from request path; add process_type validation helper |
| `src/mes_dashboard/services/yield_alert_job_service.py` | confirm/edit | if `execute_yield_alert_job` (L93-152) builds the primary query, thread `process_type` |
| `src/mes_dashboard/routes/yield_alert_routes.py` | edit | `api_yield_alert_query` (L151-257) parse+validate process_type; trend/summary serve from spool; alert response += source_code |
| `src/mes_dashboard/sql/yield_alert/alerts.sql` | edit | add SOURCE_CODE to SELECT/GROUP BY |
| `src/mes_dashboard/sql/yield_alert/trend.sql`, `summary.sql` | edit/delete | live-Oracle path retired (SCRAP_QTY/YIELD_PCT removal already in uncommitted diff) |
| `src/mes_dashboard/routes/spool_routes.py`, `src/mes_dashboard/core/spool_routes.py` | confirm-only | `yield_alert_dataset` already in `_ALLOWED_NAMESPACES`; confirm test parametrization (D1) |
| `frontend/src/yield-alert-center/App.vue` | edit | process_type selector UI; LOT column; PageHeader removal + onSort→runQuery(1) already in diff |
| `frontend/src/yield-alert-center/useYieldAlertDuckDB.ts` | edit | new spool shape (process_type, SOURCE_CODE, REJECT_LINKED) |
| `frontend/src/yield-alert-center/utils.ts` | edit | LOT/source_code formatting as needed |
| `frontend/src/shared-composables/useFilterOrchestrator.ts` | edit (additive) | process_type param pass-through only |

## Contract Updates

- API: api-contract.md (contract-reviewer); regen `contracts/openapi.json` (`cdd-kit openapi export`) after confirming alert-row field names; recapture `tests/contract/response-samples.json` (IP-5).
- CSS/UI: confirm-only — reuse `.theme-yield-alert` scope, no new rule (css-contract Rule 6).
- Env: not applicable.
- Data shape: data-shape-contract.md §3.16 (contract-reviewer); implementation must match §3.16.1 column schema.
- Business logic: business-rules.md YA-01..YA-09 (contract-reviewer); implementation must satisfy each.
- CI/CD: confirm-only — rollback `rm` step + namespace test already covered (ci-gates §Rollback Policy).

## Backend Implementation Steps (TDD — write the failing test first per row)
- B1: Bump `_SCHEMA_VERSION` 4→5 (integer constant, not env var). Pin with `test_schema_version_bumped` (value 5). YA-09 / §3.16.
- B2: Add `process_type` to `_load_primary_detail_df` + `execute_primary_query` + `_make_query_id`: MOVETXN→MOVETXN_DETAIL; `WIP_ENTITY_NAME LIKE :process_type` (replaces hardcoded `'GA%'`); add SOURCE_CODE to SELECT+GROUP BY; remove `PACKAGE IS NOT NULL`; inline REJECT_LINKED join reproducing the old upper/trim workorder normalization (design.md §Open Risks). Tests: `test_primary_query_process_type_ga/gc_filters_entity_name`, `test_source_code_not_null_rows_have_tx_zero`, `test_reject_linked_column_present_in_spool_row`, `test_ga_pct_package_na_count_is_zero`, `test_gc_pct_package_na_retained`, `test_ga_pct_totals_match_baseline`.
- B3: Update `alerts.sql` SOURCE_CODE; finalize trend.sql/summary.sql as spool-only.
- B4: Route validation in `api_yield_alert_query`: absent→GA% default; invalid→VALIDATION_ERROR. Tests: `test_query_rejects_invalid_process_type`, `test_query_forwards_process_type_kwarg` (per-kwarg `call_args.kwargs`).
- B5: Retire live trend/summary Oracle path; serve from spool. Tests: `test_query_yield_trend_no_longer_calls_oracle`, `test_query_yield_summary_no_longer_calls_oracle`, `test_trend_serves_from_spool_not_oracle`, `test_summary_serves_from_spool_not_oracle`. Verify `_query_filtered_scrap_trend`/`_query_filtered_scrap_total` and `_compute_reject_linkage`/`execute_linkage_query` are NOT called at view-serve time.
- B6: Thread `source_code` through service→alert response; confirm field name before B7.
- B7: Regenerate `contracts/openapi.json` (`cdd-kit openapi export`).
- B8: Recapture `tests/contract/response-samples.json` (alert sample with `source_code`).
- Test Update Contract (test-plan.md): delete `test_compute_reject_linkage_batches_workorders_for_oracle_in_limit`; update `test_query_yield_trend_uses_movetxn_for_transaction_and_filtered_detail_for_scrap` to assert the spool path.

## Frontend Implementation Steps
- F1: Add GA%/GC% process_type selector in primary query section (App.vue); reuse `.theme-yield-alert` scope + existing shared component.
- F2: Pass `process_type` in `POST /api/yield-alert/query` body (default GA%).
- F3: Update `useYieldAlertDuckDB.ts` for new spool schema (process_type, SOURCE_CODE, REJECT_LINKED).
- F4: Add LOT ID column (source_code) to alert table in App.vue.
- F5: Update cross-filter tests. Tests: `test_process_type_selector_propagates_to_all_views`, `test_other_filter_orchestrator_consumers_unaffected`; validation: add `source_code` to `ALERT_ITEM_SHAPE`, `test_alert_item_includes_source_code_field`, `test_process_type_param_accepted_in_query_schema`.
- F6: Confirm `useFilterOrchestrator.ts` change is additive-only (grep consumers; no signature break).

## Test Execution Plan

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 | tests/test_yield_alert_routes.py::test_query_rejects_invalid_process_type | invalid→VALIDATION_ERROR |
| AC-1 | tests/test_yield_alert_routes.py::test_query_forwards_process_type_kwarg | per-kwarg forwarding |
| AC-2 | tests/test_yield_alert_service.py::test_query_yield_trend_no_longer_calls_oracle | no Oracle call |
| AC-3 | tests/test_yield_alert_dataset_cache.py::test_ga_pct_totals_match_baseline | TX=70,494,377 SCRAP=81,972 |
| AC-4 | tests/test_yield_alert_dataset_cache.py::test_source_code_not_null_rows_have_tx_zero | TX=0 invariant |
| AC-5 | tests/test_yield_alert_dataset_cache.py::test_reject_linked_column_present_in_spool_row | column present |
| AC-6 | tests/test_yield_alert_dataset_cache.py::test_schema_version_bumped | value == 5 |
| AC-7 | tests/test_yield_alert_dataset_cache.py::test_ga_pct_package_na_count_is_zero | GA% NA=0; GC% retained |
| AC-8 | frontend/tests/yield-alert/App.cross-filter.test.js | orchestrator consumers unaffected |

Required test phases: collect, targeted, changed-area (always); contract phase applies (response-shape change). Full ladder + stress/soak (Tier 3/4, non-blocking) per test-plan.md §Test Families and references/sdd-tdd-policy.md. Implementation agents generate evidence via `cdd-kit test run`.

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.

## Known Risks

- REJECT_LINKED join must reproduce the old `_compute_reject_linkage` upper/trim workorder normalization or linkage counts drift silently (design.md §Open Risks).
- 2.4x spool volume (~1M rows/month GA%) — build time + DuckDB query latency validated by stress/soak lanes (Tier 3/4), not pre-merge.
- GC% PACKAGE=NA must be retained; PACKAGE-filter removal verified safe for GA% only (YA-03; cover with `test_gc_pct_package_na_retained`).
- Uncommitted pre-edits (App.vue PageHeader removal, onSort→runQuery(1), trend/summary SCRAP_QTY/YIELD_PCT removal) are part of this change's diff and must be covered by its tests.
- CER-001/CER-002 in context-manifest are `pending`; backend test filenames and `yield_alert_job_service.py` are confirmed present via code-map — no expansion needed for planning, but backend-engineer should confirm before editing the job service.
