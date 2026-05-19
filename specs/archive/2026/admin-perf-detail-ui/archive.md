# Archive: admin-perf-detail-ui

**Cold Data Warning**: This archive is historical evidence. Current requirements live in contracts/ and active project guidance.

## Change Summary

Added Redis diagnostic and DuckDB telemetry panels to the admin dashboard performance tab. CacheTab gained three new SummaryCards (逐出鍵數, 過期鍵數, 碎片率) plus a formatted Redis slowlog list. PerformanceTab gained a DuckDB SectionCard showing temp directory size and memory limit, with a "未啟用" fallback when DuckDB is unavailable. This rendered data already collected by the backend (fix-admin-dashboard, v1.8.0 API).

## Final Behavior

- CacheTab: 碎片率 shows `toFixed(2)` value; 逐出鍵數 / 過期鍵數 show integer counts. Slowlog list renders formatted duration strings (μs/ms/s via shared `formatDuration`); shows "無慢查詢記錄" when null or empty.
- PerformanceTab: DuckDB SectionCard shows temp_dir_bytes formatted via `formatBytes`; shows "未啟用" SectionCard when `perfDetail.duckdb` is null.
- CSS grid layout: Redis metrics split into 4-card (primary) + 3-card (secondary) SummaryCardGroup to avoid asymmetric 7-in-2 grid. DuckDB uses 2-card SummaryCardGroup.
- `@ts-expect-error` applied on JS SFC imports in PerfDetail.test.ts (TS7016; pre-existing pattern throughout the codebase).

## Final Contracts Updated

- `contracts/css/css-inventory.md` 1.2.1 → 1.2.2: added pre-existing `admin-pages/style.css` to Route-Local table (gap fix, not a new file).

## Final Tests Added / Updated

`frontend/src/admin-dashboard/tabs/__tests__/PerfDetail.test.ts` extended to 10 test cases:
- AC-1/2: Redis evicted/expired keys render numeric values
- AC-3a: fragmentation ratio renders `toFixed(2)` string
- AC-3b/c: null redis renders "-" (no crash)
- AC-4: slowlog list renders duration strings from formatDuration
- AC-5a: null slowlog renders "無慢查詢記錄"
- AC-5b: empty slowlog array renders "無慢查詢記錄"
- AC-6: null perfDetail renders gracefully
- AC-7: null duckdb shows "未啟用" card
- AC-8: no files under `contracts/` modified by this change (reviewer assertion, not automated)

## Final CI/CD Gates

| gate | result |
|---|---|
| vitest | 356 passed (incl. 10 PerfDetail cases), 1 skipped, 0 failed |
| css:check | 0 errors, 47 pre-existing warnings |
| type-check | 2 pre-existing TS7016 (JS SFC imports); continue-on-error: true |
| cdd-kit validate | All validations passed |
| cdd-kit gate | PASSED |

## Production Reality Findings

- Backend was already delivering the data (`/api/admin/perf-detail` v1.8.0) but no frontend consumed it. The two backend fixes (redis-py bytes encoding, duckdb memory_limit_state returning dict instead of string) were committed in `93a1850` before this UI change.
- ui-ux-reviewer found 2 must-fix (slowlog missing heading + browser bullets; DuckDB silently hidden when null) and 4 should-fix (English labels, no fragmentation tooltip, 7-in-2 asymmetric grid, muted placeholder). All 6 applied before QA.
- `memory_limit_state` type conflict: change-classification.md described it as `object{...}` but contracts/api and contracts/data specify it as `string|null`. AC-5 corrected by contract-reviewer before implementation.
- vi.mock path in test file: paths are relative to the test file location (`src/admin-dashboard/tabs/__tests__/`), requiring 3 levels up (`../../../`) to reach `src/admin-shared/`. Using 2 levels silently falls back to the real module with no mock-resolution error; tracked in frontend-engineer agent-log.

## Lessons Promoted to Standards

None. All findings are component-specific implementation details. The vi.mock path depth gotcha is a Vitest known behaviour (documented in Vitest docs). The TS7016 @ts-expect-error pattern is already covered by TypeScript Notes in CLAUDE.md.

## Follow-up Work

None identified. All backlog items from admin-dashboard-ux (window.alert, sticky header, banner CSS) apply to a future iteration.
