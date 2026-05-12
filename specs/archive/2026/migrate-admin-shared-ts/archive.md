---
change-id: migrate-admin-shared-ts
archived: 2026-05-12
phase: 1d
---

# Archive — migrate-admin-shared-ts

> **Cold Data Warning**: This archive is historical evidence. Current requirements live in `contracts/` and active project guidance.

## Change Summary

Phase 1d of the TypeScript migration series. Renamed `useAdminData.js → useAdminData.ts`, converted 4 Vue SFCs (`GaugeBar.vue`, `StatCard.vue`, `StatusDot.vue`, `TrendChart.vue`) to `<script setup lang="ts">` with typed `defineProps`, created a complete `index.ts` barrel (4 components + 8 composable named exports), and fixed 6 stale `.js` import specifiers in `admin-dashboard/tabs/` consumers. No runtime behaviour changed — pure TypeScript annotation refactor.

## Final Behavior

`frontend/src/admin-shared/` is now fully TypeScript. The `frontend-type-check` gate scope now includes `src/admin-shared/**/*` (5 modules under `strict: true`). All 6 consumer tabs in `admin-dashboard/` import via extension-free specifiers. A complete barrel is available for future index-based imports.

## Final Contracts Updated

- `contracts/ci/ci-gate-contract.md` — schema-version bumped to 1.3.2; Phase 1d Gate Compatibility Notes section added documenting `tsconfig.json` include expansion to `src/admin-shared/**/*`.
- `contracts/CHANGELOG.md` — `[ci 1.3.2]` entry added.

## Final Tests Added / Updated

No new test files. Existing coverage:
- `frontend/tests/legacy/admin-dashboard.test.js` — 35 assertions, all passed
- `frontend/tests/legacy/admin-performance.test.js` — included in 35 count
- `frontend/tests/legacy/admin-user-usage-kpi.test.js` — included in 35 count
- `npm run type-check` — 0 errors (tsconfig include expanded)
- `npm run build` — exit 0

## Final CI/CD Gates

All Tier 1 gates passed (local + CI):
- frontend-unit, frontend-legacy, css-governance, frontend-build — PASSED (local)
- contract-validate, cdd-strict-gate, playwright-resilience, playwright-data-boundary, playwright-critical-journeys — PASSED (CI)
- frontend-type-check (informational) — PASSED

## Production Reality Findings

- No surprises. Migration followed Phase 1b/1c pattern exactly.
- `@ts-expect-error` not needed: admin-shared imports exclusively from `core/` (Phase 1a complete), so no cross-phase suppression placeholders were required.
- QA noted `DataFetcher<unknown>` return types as acceptable-now-but-improvable; deferred to a future cleanup pass.
- Barrel exported but not yet adopted by consumers (they still import directly). Not a blocker — barrel is available for future refactoring.

## Lessons Promoted to Standards

_(to be filled after Step 3 review)_

## Follow-up Work

- Future cleanup: replace `DataFetcher<unknown>` with concrete payload interfaces in `useAdminData.ts`.
- Future refactor: migrate `admin-dashboard/tabs/` consumers to use the index barrel instead of direct path imports.
- Residual `.js` specifiers for `core/` imports in admin consumer apps: pre-existing debt, out of scope.
