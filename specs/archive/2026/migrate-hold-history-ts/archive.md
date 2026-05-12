---
change-id: migrate-hold-history-ts
schema-version: 0.1.0
archived: 2026-05-12
---

# Archive — migrate-hold-history-ts

## Change Summary

Migrated `frontend/src/hold-history/` from JavaScript to TypeScript as Phase 3 item #2 of the project-wide TypeScript migration plan. Files renamed: `main.js → main.ts`, `useAutoRefresh.js → useAutoRefresh.ts` (in-place, local API diverges from shared composables), `useHoldHistoryDuckDB.js → useHoldHistoryDuckDB.ts`. All 8 component SFCs gained `<script setup lang="ts">` with `defineProps<T>()` and `defineEmits<T>()`. `frontend/tsconfig.json` include expanded to cover `src/hold-history/**/*`. CI gate contract bumped to 1.3.6. No behaviour change was introduced; this was a pure rename+type migration.

## Final Behavior

The system behaves identically to before. TypeScript compilation now covers `frontend/src/hold-history/` under `vue-tsc --noEmit` (`npm run type-check`). 0 type errors. 270/270 Vitest tests pass. All three pre-merge CI gates pass.

## Final Contracts Updated

- `contracts/ci/ci-gate-contract.md`: schema-version 1.3.5 → 1.3.6; appended Gate Compatibility Note for Phase 3 hold-history tsconfig scope expansion.
- `contracts/CHANGELOG.md`: [ci 1.3.6] entry added. [ci 1.3.5] entry backfilled (was missing from migrate-reject-history-ts close-out).

## Final Tests Added / Updated

No new tests added. Existing test suite (270 tests) confirmed passing with no regressions (Vitest + HoldMatrix.test.js + useHoldOverview.validation.test.js).

## Final CI/CD Gates

| Gate | Command | Result |
|---|---|---|
| frontend-unit | `cd frontend && npm run test` | 270/270 PASS |
| css-governance | `cd frontend && npm run css:check` | 0 violations |
| playwright-critical-journeys | `npx playwright test hold-overview / reject-history / query-tool` | All pass (CI) |
| frontend-type-check (informational) | `cd frontend && npm run type-check` | 0 errors |

## Production Reality Findings

1. **useAutoRefresh triplication**: Three distinct `useAutoRefresh` implementations exist — hold-history local (`{ intervalMs, fetchFn } → { start, stop, lastRefreshAt, isStale, missCount }`), `shared-composables/useAutoRefresh.ts`, and `wip-shared/composables/useAutoRefresh.ts`. All three have divergent APIs. In-place rename to `.ts` was the correct decision for a Tier 3 migration. Consolidation is a future tracked change.

2. **DuckDB client already .ts**: `core/duckdb-client.ts` was already TypeScript (migrated in Phase 1a). No `@ts-expect-error` was needed to import `DuckDBClient` — evidence that the existing CLAUDE.md rule ("use `@ts-expect-error` only when wrapping a `.js` from an unmigrated directory") is correctly scoped.

3. **TODO:type count discrepancy**: Agent-log reported 14 logical annotation points; source contains 22 physical comment lines. The difference is due to multiple echarts callback sites per file (DailyTrend: 3, DurationChart: 4, ReasonPareto: 3). QA confirmed this is expected. Future qa-reviewers should count logical annotation points (one per code site), not physical comment lines.

4. **14 TODO:type annotations**: All server API response shapes (`/query`, `/view`, `/config`, `/export`, snapshot, list, trend) remain untyped in `frontend/src/types/`. Debt clears when server API types are promoted and hold-history adopts them; no action from this migration.

## Lessons Promoted to Standards

1. **TODO:type logical vs physical count** — promoted to `CLAUDE.md` TypeScript Migration Rules.
   - Rule: Count logical annotation sites (one per code location), not physical comment lines. Echarts files produce 3–4 physical lines per logical point.
   - Evidence: `specs/changes/migrate-hold-history-ts/qa-report.md` Non-blocking Observation #1; `agent-log/frontend-engineer.yml` todo_type_annotations.
   - Target: CLAUDE.md → TypeScript Migration Rules (appended after echarts callback rule).

## Follow-up Work

- Formal typing of hold-history server API responses (all 7 untyped endpoints) — requires a separate API contract update change.
- useAutoRefresh consolidation — three divergent implementations; requires behavioral analysis and separate tracked change.
- TypeScript migration Phase 3 item #3 onwards (remaining feature apps not yet migrated).

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/` and active project guidance (`CLAUDE.md`).
