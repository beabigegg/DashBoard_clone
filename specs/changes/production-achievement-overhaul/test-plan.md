---
change-id: production-achievement-overhaul
schema-version: 0.1.0
last-changed: 2026-07-14
risk: high
tier: 0
---

# Test Plan: production-achievement-overhaul

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 | unit, contract, data-boundary | tests/test_production_achievement_unified_job.py::TestSpoolSchema | 0 |
| AC-2 | unit, data-boundary | tests/test_production_achievement_package_lf_service.py | 0 |
| AC-3 | unit, data-boundary | tests/test_production_achievement_workcenter_merge_service.py | 0 |
| AC-4 | unit, integration | tests/test_production_achievement_daily_plan_service.py | 0 |
| AC-5 | contract | tests/test_production_achievement_routes.py | 1 |
| AC-6 | contract | tests/contract/test_production_achievement_contract.py | 1 |
| AC-7 | integration | tests/test_production_achievement_daily_cache.py | 1 |
| AC-8 | unit, e2e | frontend/src/production-achievement/__tests__/useProductionAchievement.test.ts | 0 |
| AC-9 | unit | frontend/src/production-achievement/__tests__/PlanAchievementStackedChart.test.ts | 0 |
| AC-10 | unit, data-boundary | frontend/src/production-achievement/__tests__/useProductionAchievementDuckDB.test.ts | 0 |
| AC-11 | unit, e2e | frontend/tests/playwright/production-achievement-settings.spec.ts | 1 |
| AC-12 | unit, data-boundary | tests/test_production_achievement_unified_job.py::TestChunkSeamReaggregation | 0 |
| AC-13 | contract | tests/contract/test_production_achievement_contract.py | 1 |

Note: AC-6's endpoint count is **10** in the current api-contract.md (`known-workcenter-groups`, OD-8, was added after change-classification.md's AC-6 text was written and said "9") — this plan tests all 10.

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | pure logic: PA-09/10/11/12/13 formulas, D1/D2 map resolution, D6 chunk math, JS pure-mirror (rollup, resolveMonthPeriod, computeDailyView/CumulativeView) |
| contract | 1 | 10 new endpoint rows, schema-version pin (1→2), 5-inline-map envelope, sample regeneration, openapi export re-run |
| integration | 1 | MySQL roundtrip ×3 tables, filter_cache reuse, warm-cache module, `_WARMUP_JOBS` registry, RQ async — all mock-bounded, no `pytestmark=integration_real` |
| e2e | 1 | Playwright rewrites for the 4-mode page + new settings page + route-registration parity |
| data-boundary | 1 | D1/D2 opposite defaults, empty-result 5-col schema, chunk-seam fixture, dual-tier parity, daily_plan_qty validation |
| resilience | 1 | MySQL read-degrade/write-503 for 3 tables, warm-cache-miss→202 fallback, flag-off no-op, progress_report() no-op proof |
| monkey | 1 | rewritten monkey spec: 4-mode rapid-click + settings CRUD adversarial input |
| stress | 4 | warmup-scheduler +2 jobs load, chunk-boundary stress (weekly/manual) |
| soak | not required | classification marks this "consider" only (low-frequency, fail-safe hourly cache) — no soak file planned, see Out of Scope |

## Test Files and Names

Backend covers: SQL/worker chunk-seam (PA-09 grain widening + D6), the 3 new MySQL services + filter_cache extension + warm-cache module (5 files total, mirroring `test_production_achievement_target_service.py`), route tests for all 10 new endpoints, contract-sample regeneration, schema-version pin.

### Backend
- `tests/test_production_achievement_unified_job.py::TestSpoolSchema` — update `test_parquet_columns_are_output_date_shift_code_specname_actual_output_qty` (5 cols incl. PACKAGE_LF) and `test_schema_version_constant_pinned` (1→2); both are Test Update Contract items (PA-09).
- `tests/test_production_achievement_unified_job.py::TestChunkSeamReaggregation` — new `test_closing_chunk_included_zero_leakage_next_day`, `test_pre_fix_undercount_fixture_now_corrected`, `test_build_chunk_sql_binds_full_datetime_chunk_end_excl` (D6/PA-15).
- `tests/test_production_achievement_service.py::TestGroupingAndWorkcenterGroupResolution` — extend `test_grouping_by_output_date_shift_workcenter_group` to assert PACKAGE_LF passthrough.
- `tests/test_production_achievement_package_lf_service.py` (new) — `test_absent_raw_falls_back_to_self`, `test_null_blank_raw_to_weizonglei_sentinel`, `test_four_confirmed_merges_resolve`, `test_upsert_unique_key_raw_package_lf`, `test_read_degrades_empty_when_ops_disabled`, `test_write_raises_mysqlunavailableerror_when_ops_disabled` (PA-09/D1).
- `tests/test_production_achievement_workcenter_merge_service.py` (new) — `test_twelve_seeded_groups_present`, `test_each_of_fifteen_excluded_groups_absent`, `test_inner_join_not_left_join_semantics`, `test_read_degrades_empty_when_ops_disabled` (PA-10/D2).
- `tests/test_production_achievement_daily_plan_service.py` (new) — `test_upsert_unique_key_workcenter_package_lf_group`, `test_coexists_with_targets_table_no_cross_write`, `test_negative_qty_rejected_before_mysql`, `test_read_degrades_empty_null_qty_when_ops_disabled` (PA-11).
- `tests/test_filter_cache_generic.py` — new `test_package_lf_values_loaded_via_shared_load_cache_orchestration` (extends existing TTL/Redis-L2/Oracle-fallback classes for the new cache key).
- `tests/test_production_achievement_daily_cache.py` (new) — `test_cache_hit_returns_without_run_or_oracle_call`, `test_cache_miss_triggers_job_run_exactly_once`, `test_flag_off_no_ops_without_importing_worker_module`, `test_progress_report_override_never_calls_update_job_progress` (PA-14).
- `tests/test_spool_warmup_scheduler.py` — new `test_warmup_jobs_include_production_achievement_today_and_yesterday`; update `test_warmup_jobs_total_count_after_duckdb_additions` (+2 entries); `test_production_history_not_in_warmup_jobs` unchanged, must still pass.
- `tests/test_production_achievement_routes.py` — new `TestPackageLfMapRoutes` / `TestWorkcenterMergeMapRoutes` (each: get-forwards, put-forwards-kwargs, put-403-not-whitelisted, delete-forwards-url-encoded-raw, delete-403-not-whitelisted), `TestDailyPlansRoutes` (put-forwards-kwargs, put-403), `TestKnownPackageLfValuesRoute`, `TestKnownWorkcenterGroupsRoute` (OD-8) each `test_get_returns_success`; update `TestReportRoute::test_spool_hit_response_shape_has_spool_download_url_spec_map_targets_map` for 5 inline maps.
- `tests/contract/test_production_achievement_contract.py` (new, mirrors `test_uph_performance_contract.py`) — `test_all_ten_new_endpoint_rows_present_in_api_contract`, `test_report_response_schema_lists_five_inline_arrays`, `test_schema_version_bump_recorded_in_compatibility_notes`; extend `tests/contract/test_schema_coverage.py` / `test_openapi_schema_resolution.py` for the 6 new response schemas; `tests/contract/samples/` regenerated via `capture_samples.py` for all 10 endpoints (never hand-edited).
- `tests/acceptance/test_production_achievement_overhaul_acceptance.py` (new) — acceptance-driver reading `acceptance.yml`; blocked/non-authoritative until a human fills real cases (currently a placeholder).

### Frontend
- `frontend/src/production-achievement/__tests__/useProductionAchievementDuckDB.test.ts` — new: D1 raw PACKAGE_LF absent falls back to itself; D1 NULL/blank resolves to `(未分類)`; D2 raw workcenter_group absent is excluded (INNER JOIN); D1/D2 join-kind not swapped; computeDailyView sums D+N into daily 產出; computeDailyView null/zero-rate guards (missing-plan/zero-plan/zero-actual); computeCumulativeView aggregate-then-divide vs. a deliberately-wrong mean-of-percentages fixture (D3); computeCumulativeView elapsed_days scaling.
- `frontend/src/production-achievement/__tests__/useProductionAchievement.test.ts` — new: resolveMonthPeriod 1st-of-month → full previous month; resolveMonthPeriod non-1st day → `[1st, referenceDate]`; range end_date capped at `min(end_date, today)`; today/yesterday → computeDailyView, month/range → computeCumulativeView; OD-3 mode/station change auto-runs; OD-4 mode/station change mid-202-poll ignored until resolved; default workcenter_group is 焊接_DB.
- `frontend/src/production-achievement/__tests__/App.test.ts` (rewrite) — 4-mode button wiring + default lands on today; range-only date inputs visible only in 自訂區間; 設定 button navigates to `/production-achievement-settings`; OD-7 mode/station preserved on return from settings; OD-11 KPI cards reuse the PA-12/13 formula (never re-aggregate independently).
- `frontend/src/production-achievement/__tests__/PlanAchievementStackedChart.test.ts` (new) — props map to a real (non-normalized) stacked series; series segments can exceed 100% for over-plan; markLine at y=100 labeled 計畫 present; colors resolved via `resolveCssVar`, not inline `rgb()`.
- `frontend/src/production-achievement-settings/__tests__/App.test.ts` (new) — fetch/PUT/CSRF wiring per tab; editForbidden flips read-only on first 403; OD-5 propagation-delay note shown after save; OD-6 no unsaved-edit navigation guard.
- `frontend/src/production-achievement-settings/components/__tests__/PackageLfMappingPanel.test.ts` (new) — renders exception rows + known-unmapped hint list; inline edit/delete emit correct payload.
- `frontend/src/production-achievement-settings/components/__tests__/WorkcenterMergeMappingPanel.test.ts` (new) — full raw-group list with include/exclude toggle (OD-8); merged-name input.
- `frontend/src/production-achievement-settings/components/__tests__/DailyPlanPanel.test.ts` (new) — OD-12: workcenter_group/package_lf_group are constrained dropdowns, no free-text option.

### E2E / Playwright
- `frontend/tests/playwright/production-achievement.spec.js` (ground-up rewrite) — 4-mode render, per-mode table columns, chart render.
- `frontend/tests/playwright/production-achievement-async.spec.ts` (rewrite) — 202-poll re-fetch takes the 5-inline-map 200 path.
- `frontend/tests/playwright/production-achievement-settings.spec.ts` (new) — whitelisted-edit path across all 3 tables; non-whitelisted read-only path (403 flips editForbidden).
- `frontend/tests/playwright/production-achievement-monkey.spec.ts` (rewrite) — rapid mode/station switching; settings-page rapid CRUD clicks.
- `frontend/tests/legacy/portal-shell-navigation.test.js` (extend) — `/production-achievement-settings` present in `STANDALONE_DRILLDOWN_ROUTES`, no drawer entry.
- `frontend/tests/production-achievement-settings-registration.test.js` (new) — `vite.config.ts` INPUT_MAP, `routeContracts.js`, `page_status.json`, `route_scope_matrix.json`, `asset_readiness_manifest.json` all agree on the new route (registry parity, complements the navigationState.js check above; 7 locations total per implementation-plan, 6 registries + 1 code-path check).

### Data-boundary
- `frontend/tests/playwright/data-boundary/production-achievement-data-boundary.spec.js` (extend) — `daily_plan_qty` negative/non-numeric input rejected client-side before PUT fires.
- `tests/test_production_achievement_package_lf_service.py` / `tests/test_production_achievement_workcenter_merge_service.py` — D1/D2 opposite-default edge cases (see Backend).
- `tests/test_production_achievement_unified_job.py::TestSpoolSchema` — empty-result 5-column schema fallback (0 rows, valid parquet, never omitted/errored).
- `tests/test_frontend_production_achievement_parity.py::TestProductionAchievementRollupParity` — new `test_multiple_package_lf_per_specname_day_parity` (dual-tier, unequal-plan-magnitude fixture).
- `tests/property/test_production_achievement_aggregate_invariant.py` (new, hypothesis) — property: aggregate-then-divide ≠ mean-of-percentages whenever per-group plan magnitudes differ (generalizes the one hand-picked D3 fixture above across generated cases).

### Resilience
- `tests/integration/test_production_achievement_mysql_roundtrip.py` (extend) — new `TestPackageLfTableRoundtrip`, `TestWorkcenterMergeTableRoundtrip`, `TestDailyPlanTableRoundtrip` (write-then-read roundtrip; ops-disabled read→empty; ops-disabled write→503; mirrors `TestTargetTableRoundtrip`).
- `tests/integration/test_production_achievement_resilience.py` (extend) — cache-miss falls through to the existing 202 path seamlessly; empty `workcenter_merge_map` → whole report renders empty (OD-9, not an error).
- `frontend/tests/playwright/resilience/production-achievement-resilience.spec.js` (extend) — MySQL-down degrade for the 3 new tables; settings write-503 vs. read-empty-array distinction.

### Stress
- `tests/stress/test_production_achievement_stress.py` (extend) — warmup-scheduler load with the 2 added hourly jobs alongside the existing 6, no cross-job monopolization.
- `tests/stress/test_chunk_boundary.py` (new) — many-day range at stress-scale chunk counts; D6 closing chunk included exactly once per query; zero leakage/duplication across every seam.

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
| tests/test_production_achievement_routes.py::TestReportRoute::test_spool_hit_response_shape_has_spool_download_url_spec_map_targets_map | update | AC-6: envelope grows from 2 to 5 inline arrays (data-shape §3.28.4) |
| tests/test_production_achievement_unified_job.py::TestSpoolSchema::test_parquet_columns_are_output_date_shift_code_specname_actual_output_qty | update | AC-1: grain widens from 4 to 5 columns (+PACKAGE_LF, PA-09) |
| tests/test_production_achievement_unified_job.py::TestSpoolSchema::test_schema_version_constant_pinned | update | AC-1: `_PA_SPOOL_SCHEMA_VERSION` 1 → 2 |
| tests/test_spool_warmup_scheduler.py::test_warmup_jobs_total_count_after_duckdb_additions | update | AC-7: `_WARMUP_JOBS` gains 2 entries |
| tests/test_production_achievement_routes.py::TestFilterOptionsRoute (get_filter_options `workcenter_groups`) | update | Phase 1: `workcenter_groups` redefined in place to the merged (D2) list |

## Stop Rules

- Do not run broad pytest before targeted and changed-area phases pass.
- Do not investigate more than the first failure per phase.
- Do not classify any failure as known, pre-existing, waived, or allowed.
- If full suite fails, record the first failure and block the gate.

## Out of Scope

- Month-mode (當月/自訂區間) warm-caching — explicitly out of scope per the approved plan (D5); only today/yesterday are pre-warmed. No test asserts month-mode cache-hit behavior.
- Pixel-level / screenshot visual assertions for the chart and settings page — owned by visual-reviewer's visual-review-report.md; this plan covers only functional/structural chart assertions (option shape, markLine, >100% segments).
- Soak testing — classified "consider," not required (low-frequency, fail-safe hourly warm-cache); no soak test file is planned.
- PA-04 three-shift historical-regime `output_date` rule — unverified assumption, already out of scope per business-rules.md, unaffected by this change.
- `production_history`'s own warmup exclusion — regression-covered by the unchanged `test_production_history_not_in_warmup_jobs`, not re-litigated here.
- OD-9/OD-10 (no config-down read-time discriminator) — confirmed no-op decisions; no new test surface beyond the existing empty-array/503 behavior already listed above.

## Notes

- D1 (`package_lf_map`, LEFT JOIN, fallback-to-self) vs. D2 (`workcenter_merge_map`, INNER JOIN, exclude-by-absence) are opposite defaults on purpose — every test touching either must assert "not the other join kind," not just its own happy path.
- D3 (cumulative trend aggregate-then-divide) looks correct on a single-group fixture and silently wrong on a multi-group one — both the property test and the deliberately-wrong mean-of-percentages fixture are required.
- D6 (closing-chunk) changes historical N-shift numbers; its regression test must assert the corrected total, not just the presence of new rows.
- Tier column uses this repo's 0 (unit, <30s, local) / 1 (contract+critical-path, PR-required) / 2 (visual) / 3 (nightly real-infra) / 4 (weekly/manual) scale; most `tests/integration/*production_achievement*` files are mock-bounded (no `pytestmark=integration_real`) and run at tier 1, not nightly.
- `tests/acceptance/` coverage is only as good as `acceptance.yml`, still a human-authored placeholder as of this plan — flag to qa-reviewer if it remains unfilled at gate time.
