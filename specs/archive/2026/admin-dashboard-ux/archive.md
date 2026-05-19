# Archive: admin-dashboard-ux

**Cold Data Warning**: This archive is historical evidence. Current requirements live in contracts/ and active project guidance.

## Change Summary

Refactored the admin dashboard Vue SFC tabs to prioritise critical information over historical context. Previously all six tabs placed trend charts and status grids before actionable alerts. The change reordered sections, added threshold-aware accent colours to SummaryCard, formatted Redis slowlog durations as human-readable ms/s/μs, added a "最後更新: HH:MM:SS" label to each tab, and improved TrendChart empty-state copy with a timing hint.

## Final Behavior

- OverviewTab: 系統警示 section card is first (before 系統健康總覽 and trend charts).
- WorkerTab: current-state Worker 控制 card comes before TrendChart panels.
- CacheTab: fragmentation-ratio SummaryCard threshold (warning ≥1.5, danger ≥2.0); evicted-keys threshold (warning ≥1); slowlog durations rendered as μs/ms/s strings.
- PerformanceTab: DuckDB temp-dir SummaryCard has warning threshold at 500 MB.
- All six tabs: `admin-tab__last-updated` label (role=status, aria-live=polite) shows time of last refresh.
- TrendChart empty state: two-line copy — primary "趨勢資料不足（需至少 2 筆快照）" + hint "（每 30 秒自動收集一次）".
- SummaryCard: optional `warningThreshold`, `dangerThreshold`, `thresholdValue` props (backward-compatible); `accentColor` computed replaces static accent when thresholds fire.

## Final Contracts Updated

None. All five UX changes were within existing registered contract surfaces (contract-reviewer verdict: no version bumps required).

## Final Tests Added / Updated

6 new test files (402 vitest cases total, 1 skipped):
- `frontend/src/admin-shared/utils/__tests__/formatDuration.test.ts` (7 boundary cases)
- `frontend/src/admin-shared/composables/__tests__/useLastUpdated.test.ts` (3 cases)
- `frontend/src/admin-shared/components/__tests__/SummaryCard.test.ts` (9 threshold cases)
- `frontend/src/admin-shared/components/__tests__/TrendChart.test.ts` (5 empty-state cases)
- `frontend/src/admin-dashboard/tabs/__tests__/OverviewTab.test.ts` (5 cases — section order + last-updated)
- `frontend/src/admin-dashboard/tabs/__tests__/WorkerTab.test.ts` (4 cases — TrendChart order + last-updated)
- `frontend/src/admin-dashboard/tabs/__tests__/CacheTab.test.ts` (13 cases — slowlog formatting + thresholds + last-updated)

## Final CI/CD Gates

| gate | result |
|---|---|
| vitest | 402 passed, 1 skipped, 0 failed |
| css:check | 0 errors, 47 pre-existing warnings |
| type-check | 0 errors (clean) |
| cdd-kit gate | PASSED |

## Production Reality Findings

- CacheTab had `v-if="historyData.length > 1"` guards on both TrendChart components, which silently bypassed AC-7 (empty-state rendering). Found and fixed by ui-ux-reviewer before QA. Evidence: agent-log/ui-ux-reviewer.yml.
- "Active Alerts" renamed to "系統警示" for language consistency (all other labels were Chinese).

## Lessons Promoted to Standards

None. All findings were component-specific fixes. The TrendChart v-if-bypass finding is an implementation detail; the SummaryCard threshold prop pattern is standard Vue additive-props practice. No new rules warranted in contracts/ or CLAUDE.md.

## Follow-up Work

Non-blocking backlog from ui-ux-reviewer:
- `deadWorkerAlert` inline banner CSS inconsistency with SectionCard styling
- WorkerTab `doRestart()` error path uses `window.alert`
- LogsTab destructive confirmations use `window.confirm`/`window.alert`
- Sticky "最後更新" header for long-scrolling tabs (Logs, Usage)
