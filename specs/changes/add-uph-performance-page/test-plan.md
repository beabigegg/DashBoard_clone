---
change-id: add-uph-performance-page
schema-version: 0.1.0
last-changed: 2026-07-13
risk: high
tier: 1
---

# Test Plan: add-uph-performance-page

Templates: `test_eap_alarm_rq_async.py`, `test_production_achievement_rq_async.py`,
`test_base_job_semaphore_wiring.py` (root + integration copies), `test_production_achievement_stress.py`,
`production-achievement-async.spec.ts`, `test_eap_alarm_e2e.py`. New suites mirror these class/test shapes.

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 (nav registration at 4 points, app boots) | e2e / unit | frontend/tests/legacy/portal-shell-navigation.test.js | 0 |
| AC-2 (chunking ≤6h, LAST_UPDATE_TIME mandatory, GDBA/GWBA-only source query) | unit + integration | tests/integration/test_uph_performance_rq_async.py | 1 |
| AC-3 (family→PARAMETER_NAME mapping pinned, SEQ_ID join) | unit | tests/test_uph_performance_sql_builder.py | 0 |
| AC-4 (LOT_ID/DW_MES_CONTAINER + EQUIPMENT_ID/DW_MES_RESOURCE bridges, workcenter_groups DB/WB) | unit + integration | tests/integration/test_uph_performance_rq_async.py | 1 |
| AC-5 (always-async, no sync fallback, heavy-slot, spool namespace, env flag parity) | integration + contract | tests/integration/test_uph_performance_rq_async.py | 1 |
| AC-6 (global filters, trend group-by, independent ranking Type filter, detail table) | contract + e2e | tests/contract/test_uph_performance_contract.py | 1 |
| AC-7 (deploy/launcher wiring, env-contract/openapi sync) | contract | tests/contract/test_uph_performance_contract.py | 1 |
| AC-8 (empty-state graceful, no parameter-name leak) | data-boundary | tests/integration/test_uph_performance_data_boundary.py | 1 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | SQL builder: chunk-window ≤6h enforcement, family→PARAMETER_NAME mapping pin, no-scale-conversion pin, DB/WB structural test — `tests/test_uph_performance_sql_builder.py` |
| contract | 1 | new endpoint response-shape samples + OpenAPI schema resolution for 6 endpoints (spool, status, filter-options, product-filter-options, trend, ranking, detail) — `tests/contract/test_uph_performance_contract.py` |
| integration | 1 | RQ async dispatch, worker fn correctness, semaphore wiring, spool cache-hit/miss, route↔worker signature — `tests/integration/test_uph_performance_rq_async.py` |
| data-boundary | 1 | zero-row BondUPH/fHCM_UPH empty state; generic wording (no parameter leak); trend null-gap vs zero — `tests/integration/test_uph_performance_data_boundary.py` |
| e2e | 1 | full-stack route + Playwright flow across all confirmed states — `tests/e2e/test_uph_performance_e2e.py`, `frontend/tests/playwright/uph-performance.spec.ts` |
| resilience | 1/3 | Oracle fault mid-chunk, Redis-down → 503, worker-unavailable no fallback — `tests/integration/test_uph_performance_rq_async.py` |
| stress | 3 | new heavy worker on shared semaphore, burst + cross-worker fairness with sibling jobs — `tests/stress/test_uph_performance_stress.py` |
| soak | 4 | long-running queue soak folded into existing `tests/integration/test_soak_workload.py` workload list |
| monkey | optional | operation-sequence spec optional per classification; log via agent-log if run |

## Test Names (one line each, no body)

### Unit — tests/test_uph_performance_sql_builder.py
- test_chunk_window_never_exceeds_6h (UPH-01)
- test_missing_last_update_time_raises_or_400 (UPH-01)
- test_unbounded_date_range_rejected (UPH-01, mirrors EA-03)
- test_family_scope_restricted_to_gdba_gwba (UPH-02)
- test_family_outside_gdba_gwba_returns_400 (UPH-02, negative — GWBK/GWMT/GPTA)
- test_gdba_maps_to_bonduph_parameter_name (UPH-03, pinned)
- test_gwba_maps_to_fhcm_uph_parameter_name (UPH-03, pinned)
- test_parameter_mapping_swap_detected (UPH-03 — fails if GDBA/GWBA mapping ever swapped)
- test_uph_value_no_scale_conversion (UPH-04, exact name per business-rules.md)
- test_db_wb_label_via_workcenter_groups_not_prefix (UPH-05, exact name per business-rules.md — mirrors EA-07 regression class)
- test_db_wb_label_null_when_workcenter_unmapped (UPH-05)

### Integration — tests/integration/test_uph_performance_rq_async.py
- test_enqueue_to_uph_performance_queue (mirrors TestEapAlarmSpoolTrigger)
- test_post_spool_missing_date_returns_400
- test_post_spool_family_outside_enum_returns_400 (UPH-02)
- test_worker_fn_writes_parquet_with_correct_columns (schema §3.29)
- test_worker_fn_time_chunks_never_exceed_6h (UPH-01, structural — asserts chunk_strategy=TIME + window size)
- test_worker_fn_oracle_sql_contains_last_update_time_predicate (mirrors eap_alarm equivalent)
- test_worker_fn_bridges_container_and_resource_dims (AC-4)
- test_spool_cache_hit_returns_200
- test_spool_miss_returns_202_with_job_id
- test_spool_miss_worker_unavailable_returns_503_no_fallback (UPH-ASYNC/ASYNC-06)
- test_env_flag_off_is_pure_kill_switch_503_on_miss (UPH-ASYNC)
- test_route_forwards_families_workcenter_package_pj_type_equipment_ids_per_kwarg (per-kwarg, not assert_called_once_with)
- test_async_route_worker_signature_bind (inspect.signature(worker_fn).bind(**kwargs) — per promoted learning)
- test_ranking_endpoint_pj_type_filter_independent_of_global_pj_type (cross-filter narrowing surface)
- test_ranking_pj_type_empty_while_global_pj_type_populated (one-of-N axis EMPTY-while-sibling-populated)
- test_ranking_sorted_ascending_by_avg_uph
- test_ranking_avg_uph_null_not_zero_for_zero_sample
- test_trend_group_by_default_family
- test_trend_group_by_unknown_value_returns_400
- test_trend_missing_hour_bucket_is_null_not_zero
- test_detail_per_page_capped_at_200
- test_oracle_fault_mid_chunk_no_partial_spool (resilience, mirrors downtime/eap_alarm fault injection)
- test_redis_unavailable_returns_503_no_legacy_fallback (resilience)

### Contract — tests/contract/test_uph_performance_contract.py
- test_spool_202_envelope_matches_schema
- test_spool_200_spool_hit_envelope_matches_schema
- test_spool_503_service_unavailable_has_retry_after
- test_spool_400_validation_error_envelope
- test_filter_options_response_shape
- test_product_filter_options_response_shape
- test_product_filter_options_500_shape
- test_trend_response_shape_labels_series_group_by
- test_ranking_response_shape_items_pj_types
- test_detail_response_shape_rows_meta
- test_openapi_schema_resolves_for_all_6_endpoints (AC-7)

### Data-boundary — tests/integration/test_uph_performance_data_boundary.py
- test_zero_rows_for_bonduph_returns_empty_not_error (UPH-03/AC-8)
- test_zero_rows_for_fhcm_uph_returns_empty_not_error (UPH-03/AC-8)
- test_empty_state_message_is_generic_no_parameter_name_leak (confirmed wording, AC-8)
- test_empty_state_distinct_from_job_failed_state
- test_empty_state_distinct_from_worker_unavailable_state
- test_state_expired_410_distinct_from_state_empty

### Registry / allowlist / deploy-wiring (extend existing files, no duplicates)
- tests/test_spool_routes.py::test_uph_performance_in_allowed_namespaces (parametrized allowlist, mirrors test_eap_alarm_in_allowed_namespaces)
- tests/test_job_registry.py::test_each_service_registers_exactly_one_job_type (extend for uph_performance)
- tests/test_job_registry.py::test_uph_performance_registered_with_always_async_true (mirrors test_eap_alarm_registered_with_always_async_true)
- tests/test_query_cost_policy.py::test_no_caller_outside_tests (extend _APPROVED_CALLERS["base_chunked_duckdb_job"] with uph_performance_worker)

### Stress — tests/stress/test_uph_performance_stress.py
- test_burst_peak_bounded_no_leak (mirrors production_achievement stress)
- test_burst_no_deadlock_with_mixed_success_failure
- test_uph_and_sibling_jobs_interleave_no_monopolization (cross-worker fairness, shared semaphore)
- test_identical_date_range_concurrent_jobs_no_spool_corruption

### E2E — tests/e2e/test_uph_performance_e2e.py
- test_post_spool_missing_date_returns_400
- test_post_spool_family_outside_enum_returns_400
- test_post_spool_returns_202_async
- test_filter_options_returns_structured_options
- test_trend_returns_series_data
- test_ranking_returns_ascending_items
- test_detail_returns_paginated_rows_with_expected_fields

### Playwright — frontend/tests/playwright/uph-performance.spec.ts
- state-initial renders filter bar with no results (fast pre-render skip guard per ci-workflow.md)
- state-spooling shows cancellable AsyncQueryProgress, LoadingOverlay hidden
- state-spool-hit renders results immediately without progress bar
- state-ready-populated renders trend + ranking + detail
- state-empty shows EmptyState with confirmed generic wording, no BondUPH/fHCM_UPH text
- state-unavailable (503) shows ErrorBanner, distinct from EmptyState
- state-job-failed shows ErrorBanner, distinct from state-empty and state-unavailable
- state-validation-error (400, bad dates / family outside enum) shows inline validation
- state-expired (410) prompts re-run
- state-coarse-options-degraded shows inline warning near Package/Type dropdowns, other filters usable
- ctrl-ranking-type-filter defaults to none-selected, ranking empty until a Type is chosen
- ctrl-ranking-type-filter is visibly distinct from ctrl-type-select-global (label/placement)
- selecting ranking Type filter does not mutate or read the global Type filter state
- global Type filter populated + ranking Type filter empty renders ranking prompt, not an error
- trend legend click toggles series visibility
- trend renders a gap (not a zero line) for a null bucket
- ctrl-cancel-job cancels in-flight job and returns to prior/state-initial

## Test Execution Ladder

| phase | required | command source | max failures | result artifact |
|---|---:|---|---:|---|
| collect | yes | cdd-kit test select | 1 | test-runs/<run-id>/summary.json |
| targeted | yes | cdd-kit test select | 1 | test-evidence.yml |
| changed-area | yes | cdd-kit test select | 1 | test-evidence.yml |
| contract | if affected | cdd-kit validate | 1 | test-evidence.yml |
| quality | if configured | ci-gates.md | 1 | test-evidence.yml |
| full | final/CI | cdd-kit test run --phase full | 1 | test-evidence.yml |

## Test Update Contract

| existing test | action | reason |
|---|---|---|
| tests/test_spool_routes.py::test_allowed_namespaces_pass_namespace_validation | update | add `uph_performance` case to parametrize list (AC-5) |
| tests/test_job_registry.py::test_each_service_registers_exactly_one_job_type | update | count must include new `uph_performance` registration (AC-5) |
| tests/test_query_cost_policy.py::test_no_caller_outside_tests | update | add `uph_performance_worker` to `_APPROVED_CALLERS["base_chunked_duckdb_job"]` (AC-2) |

## Stop Rules

- Do not run broad pytest before targeted and changed-area phases pass.
- Do not investigate more than the first failure per phase.
- Do not classify any failure as known, pre-existing, waived, or allowed.
- If full suite fails, record the first failure and block the gate.

## Out of Scope
- GWBK/GWMT/GPTA family support (explicit non-goal; only negative-path 400 coverage above)
- Concurrency-knob tuning (max_parallel, HEAVY_QUERY_MAX_CONCURRENT, RQ worker count changes)
- Threshold/alert-coloring, CSV/Parquet export, summary/KPI cards, pareto chart (deleted controls, no endpoints)
- Scale-conversion "fix" attempts (UPH-04 explicitly forbids; only the pinned no-conversion test applies)
- Soak beyond folding into existing `tests/integration/test_soak_workload.py` workload list

## Notes
Structural pinning tests (UPH-03 mapping, UPH-04 no-scale, UPH-05 workcenter_groups) must fail if implementation
regresses to prefix enumeration or reintroduces scale conversion — assert on the mapping/lookup mechanism itself,
not just output values. The 3 "extend existing file" gates (spool allowlist, job-registry count, `_APPROVED_CALLERS`)
are pre-existing regression tripwires per CLAUDE.md promoted learnings — extend them in the same PR, don't fork a
duplicate test file for the same assertion.
