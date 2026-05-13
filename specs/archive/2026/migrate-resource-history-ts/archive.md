---
change-id: migrate-resource-history-ts
closed: 2026-05-13
status: done
---

# Archive — migrate-resource-history-ts

## Change Summary

Phase 3 TypeScript migration of the `frontend/src/resource-history/` feature app (10 files). All `.js` source files were renamed to `.ts` and all Vue SFCs received `<script setup lang="ts">` with fully typed props, emits, and reactive state. Stale `.js` import specifiers were replaced with extension-free specifiers throughout. `tsconfig.json` was expanded to include `src/resource-history/**/*` as item #15. The CI/CD gate contract was bumped from schema-version 1.3.8 → 1.3.9 to document the scope expansion. No runtime behavior change was introduced.

## Final Behavior

The system behaviour is unchanged. `resource-history` is now fully covered by the TypeScript type-checker (`npm run type-check`) — previously the app was excluded from tsconfig scope. All 10 files carry TypeScript annotations; known library gaps (echarts callback parameters, hierarchy node union in DetailSection.vue column descriptors) are annotated with `// TODO:` markers per project convention.

## Final Contracts Updated

| Contract | Change |
|---|---|
| `contracts/ci/ci-gate-contract.md` | schema-version 1.3.8 → 1.3.9; Gate Compatibility Note added for Phase 3 item #15 |
| `contracts/CHANGELOG.md` | `[ci 1.3.9] — 2026-05-13` entry added |

## Final Tests Added / Updated

No new test files. All existing tests pass unchanged:
- Vitest unit suite: **302/302** (zero regressions)
- CSS governance check: **0 violations** (47 pre-existing warnings unchanged)
- TypeScript type-check: **0 errors** (scope now includes `src/resource-history/**/*`)
- Legacy node:test (`frontend/tests/legacy/resource-history.test.js`): **16/16** (inline formula replicas; no import from source; no changes needed)

## Final CI/CD Gates

Per `ci-gates.md`:
- `frontend-unit` — PASSED (local + CI)
- `css-governance` — PASSED (local + CI)
- `frontend-type-check` — PASSED (local + CI; informational per Required Check Policy)
- `frontend-build` — PASSED (CI)
- `contract-validate` — PASSED (CI)
- `cdd-strict-gate` — PASSED (CI)

## Production Reality Findings

No surprises. Migration followed the established Phase 3 pattern exactly (same as `migrate-qc-gate-ts`, `migrate-resource-status-ts`, `migrate-hold-history-ts`, `migrate-reject-history-ts`, `migrate-wip-hold-ts`). CI passed cleanly and the user confirmed no runtime issues.

One minor nuance confirmed during implementation: `TrendChart.vue`'s echarts `formatter` was a string template literal (not a function callback), so no `// TODO: type echarts callback` annotation was required there — the existing CLAUDE.md rule already covers this correctly ("callback parameters … in formatter/tooltip *functions*").

A new typing pattern was established for DuckDB-WASM composables: `DuckDBClient.sendQuery()` rows are typed as `unknown[]` at the call site, then accessed within loops via `as Record<string, unknown>` casts. This avoids bare `any` while remaining compatible with the not-yet-typed DuckDB client.

## Lessons Promoted to Standards

None promoted. The one candidate (DuckDB composable row-typing pattern: `unknown[]` + inline `as Record<string, unknown>`) was reviewed by `contract-reviewer` and classified **do-not-promote**: it is the weakest of three variants present in the codebase (`useRejectHistoryDuckDB.ts` uses a local interface override; `useHoldHistoryDuckDB.ts` uses a centralized `toRows()` helper). Promoting only the resource-history inline-cast variant would give incomplete and misleading guidance. A synthesis lesson covering all three variants would be worth writing during a future DuckDB composable audit, outside this change's scope.

## Follow-up Work

- Performance optimization for `resource-history` (slow Oracle queries and 2h Redis TTL for immutable historical data): tracked as a separate change `migrate-resource-history-perf` (to be opened).

---

> **Cold Data Warning**: This archive is historical evidence. Current requirements live in `contracts/` and active project guidance (`CLAUDE.md`). Do not treat this file as a live specification.
