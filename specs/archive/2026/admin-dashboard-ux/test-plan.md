---
change-id: admin-dashboard-ux
schema-version: 0.1.0
last-changed: 2026-05-19
risk: low
tier: 0
---

# Test Plan: admin-dashboard-ux

## Acceptance Criteria — Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 | integration (DOM order) | `frontend/src/admin-dashboard/tabs/__tests__/OverviewTab.test.ts` | 0 |
| AC-2 | integration (DOM order) | `frontend/src/admin-dashboard/tabs/__tests__/WorkerTab.test.ts` | 0 |
| AC-3 | unit | `frontend/src/admin-shared/components/__tests__/SummaryCard.test.ts` | 0 |
| AC-4 | integration (prop wiring) | `frontend/src/admin-dashboard/tabs/__tests__/CacheTab.test.ts` | 0 |
| AC-5 | unit + integration | `frontend/src/admin-shared/components/__tests__/SummaryCard.test.ts` + `frontend/src/admin-dashboard/tabs/__tests__/CacheTab.test.ts` | 0 |
| AC-6 | integration (composable) | OverviewTab / CacheTab / WorkerTab test files above | 0 |
| AC-7 | unit | `frontend/src/admin-shared/components/__tests__/TrendChart.test.ts` | 0 |
| AC-8 | regression | `frontend/src/admin-dashboard/tabs/__tests__/PerfDetail.test.ts` | 0 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | Tier 0 | Pure-function and single-component render tests; < 30 s total |
| integration | Tier 0 | Tab-level `mount()` tests verifying cross-component wiring; jsdom via Vitest pragma |

## Test File Inventory

### `frontend/src/admin-shared/components/__tests__/SummaryCard.test.ts` (new — AC-3, AC-5)

- `no_thresholds_uses_static_accent`
- `below_warning_uses_static_accent`
- `at_warning_threshold_renders_warning`
- `above_warning_renders_warning`
- `at_danger_threshold_renders_danger`
- `danger_takes_precedence_over_warning`
- `non_numeric_value_with_thresholds_falls_back_to_static_accent`
- `only_warning_threshold_no_danger_class`
- `only_danger_threshold_no_warning_class`

### `frontend/src/admin-shared/components/__tests__/TrendChart.test.ts` (new — AC-7)

- `empty_state_zero_snapshots_shows_first_line`
- `empty_state_zero_snapshots_shows_second_line`
- `empty_state_one_snapshot_shows_both_lines`
- `two_snapshots_hides_empty_state_shows_canvas`
- `empty_state_second_line_is_separate_dom_node`

### `frontend/src/admin-dashboard/tabs/__tests__/OverviewTab.test.ts` (new — AC-1, AC-6)

- `active_alerts_section_is_first_section_card_in_dom`
- `active_alerts_renders_before_status_grid`
- `active_alerts_renders_before_trend_charts`
- `last_updated_label_present_after_mount`
- `last_updated_label_updates_to_new_time_after_refresh`

### `frontend/src/admin-dashboard/tabs/__tests__/WorkerTab.test.ts` (new — AC-2, AC-6)

- `all_trend_charts_render_after_memory_guard_section`
- `all_trend_charts_render_after_async_workers_section`
- `all_trend_charts_render_after_worker_control_section`
- `last_updated_label_updates_to_new_time_after_refresh`

### `frontend/src/admin-dashboard/tabs/__tests__/CacheTab.test.ts` (new — AC-4, AC-5, AC-6)

Duration formatter boundary tests (AC-5):

- `slowlog_duration_999us_renders_microsecond_suffix`
- `slowlog_duration_1000us_renders_millisecond_suffix`
- `slowlog_duration_999999us_renders_millisecond_suffix`
- `slowlog_duration_1000000us_renders_second_suffix`
- `slowlog_duration_large_renders_second_suffix_no_us_or_ms`

Threshold wiring tests (AC-4):

- `mem_fragmentation_ratio_1_5_triggers_warning_accent`
- `mem_fragmentation_ratio_2_0_triggers_danger_accent`
- `mem_fragmentation_ratio_1_49_uses_static_accent`
- `evicted_keys_1_triggers_warning_accent`
- `evicted_keys_0_uses_static_accent`
- `duckdb_temp_bytes_524288000_triggers_warning_accent`
- `duckdb_temp_bytes_below_threshold_uses_static_accent`

Last-updated (AC-6):

- `last_updated_label_updates_to_new_time_after_refresh`

### `frontend/src/admin-dashboard/tabs/__tests__/PerfDetail.test.ts` (existing — AC-8)

All 8 existing tests must pass without modification. No new tests added here.

## Out of Scope

- E2E / Playwright — UI layout reorder covered by visual-review-report artifact
- Backend API and contract changes — none introduced by this change
- CSS scoping lint — enforced by `npm run css:check` gate, not Vitest
- Other feature apps — `shared-ui/components/SummaryCard.vue` is unchanged; only `admin-shared` additions are new

## Notes

- All component tests require `// @vitest-environment jsdom` pragma (vitest.config.js defaults to `node`).
- Duration formatter should be extracted as a pure function in `admin-shared/utils/`; if so, boundary unit tests belong there and CacheTab DOM tests verify only rendered output, not re-test boundaries.
- WorkerTab DOM-order tests need `worker_memory_guard.enabled = true` in fixture so the memory-guard `v-if` SectionCard renders.
- Last-updated tests must mock `Date` before mount to produce a deterministic HH:MM:SS string for assertion.
- If `useLastUpdated` is extracted as a shared composable, add a dedicated unit test at `frontend/src/admin-shared/composables/__tests__/useLastUpdated.test.ts`.
