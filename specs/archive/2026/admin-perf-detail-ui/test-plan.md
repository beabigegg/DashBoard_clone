---
change-id: admin-perf-detail-ui
schema-version: 0.1.0
last-changed: 2026-05-19
risk: low
tier: 3
---

# Test Plan: admin-perf-detail-ui

## Acceptance Criteria → Test Mapping

| criterion id | description | test family | test file path | test name | tier |
|---|---|---|---|---|---|
| AC-1 | evicted_keys and expired_keys integers rendered in Redis section | unit | `frontend/src/admin-dashboard/tabs/__tests__/PerfDetail.test.ts` | `renders evicted_keys and expired_keys as integers` | 0 |
| AC-2 | mem_fragmentation_ratio rendered ≤2 decimal places | unit | `frontend/src/admin-dashboard/tabs/__tests__/PerfDetail.test.ts` | `renders mem_fragmentation_ratio with at most 2 decimal places` | 0 |
| AC-3a | slowlog non-empty → each entry rendered | unit | `frontend/src/admin-dashboard/tabs/__tests__/PerfDetail.test.ts` | `renders each slowlog entry when array is non-empty` | 0 |
| AC-3b | slowlog null → graceful placeholder | unit | `frontend/src/admin-dashboard/tabs/__tests__/PerfDetail.test.ts` | `renders placeholder when slowlog is null` | 0 |
| AC-3c | slowlog empty array → graceful placeholder | unit | `frontend/src/admin-dashboard/tabs/__tests__/PerfDetail.test.ts` | `renders placeholder when slowlog is empty array` | 0 |
| AC-4 | temp_dir_bytes integer rendered human-readable in DuckDB section | unit | `frontend/src/admin-dashboard/tabs/__tests__/PerfDetail.test.ts` | `renders temp_dir_bytes as human-readable size` | 0 |
| AC-5a | memory_limit_state string rendered | unit | `frontend/src/admin-dashboard/tabs/__tests__/PerfDetail.test.ts` | `renders memory_limit_state string value` | 0 |
| AC-5b | memory_limit_state null → graceful placeholder | unit | `frontend/src/admin-dashboard/tabs/__tests__/PerfDetail.test.ts` | `renders placeholder when memory_limit_state is null` | 0 |
| AC-6 | all 6 fields null → no throw, no console error, siblings intact | unit | `frontend/src/admin-dashboard/tabs/__tests__/PerfDetail.test.ts` | `all new fields null: no error thrown and sibling sections still render` | 0 |
| AC-7 | existing fields do not regress | unit | `frontend/src/admin-dashboard/tabs/__tests__/PerfDetail.test.ts` | `pre-existing performance-detail fields still render with full payload` | 0 |
| AC-8 | no contract files modified | contract (manual) | CI diff check — confirm no `contracts/` files in PR diff | n/a | 1 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | Vitest component tests; covered by `src/**/*.test.ts` glob in vitest.config.js |
| data-boundary | 0 | null and empty-array cases embedded in the unit test file above |

## New Test Files Needed

- `frontend/src/admin-dashboard/tabs/__tests__/PerfDetail.test.ts` — all 10 test cases above; mount the performance-detail component with `@vue/test-utils`, stub the API fetch, assert DOM output

## Out of Scope

- Integration tests against live `/admin/api/performance-detail` endpoint
- E2E / Playwright tests (pure additive rendering, no routing or auth changes)
- Visual regression snapshots (ui-ux-reviewer covers this in agent-log)
- Resilience, soak, and stress testing

## Notes

- AC-8 is enforced by CI PR diff check, not a Vitest test; gate: no files under `contracts/` appear in the changeset.
- The `include: ['src/**/*.test.ts']` glob in `vitest.config.js` already picks up the new `__tests__/` file — no config change needed.
- Run gate command: `cd frontend && npm run test -- --run`.
