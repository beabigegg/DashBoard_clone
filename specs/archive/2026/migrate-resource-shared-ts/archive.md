---
change-id: migrate-resource-shared-ts
archived: 2026-05-12
phase: 1e
---

# Archive — migrate-resource-shared-ts

> **Cold Data Warning**: This archive is historical evidence. Current requirements live in `contracts/` and active project guidance.

## Change Summary

Phase 1e of the TypeScript migration series. Renamed `constants.js → constants.ts` with full typed exports (`Readonly<Record<string,string>>` for maps, typed function signatures for 3 utility functions), converted `HierarchyTable.vue` and `MultiSelect.vue` to `<script setup lang="ts">` with `defineProps<T>()` generic syntax, created a complete `index.ts` barrel (2 components + 10 named exports), and fixed 5 stale `.js` import specifiers in `resource-history/` and `resource-status/` consumers. No runtime behaviour changed — pure TypeScript annotation refactor.

## Final Behavior

`frontend/src/resource-shared/` is now fully TypeScript. The `frontend-type-check` gate scope now includes `src/resource-shared/**/*` (3 modules under `strict: true`). All 5 consumer files reference constants and components via extension-free specifiers.

## Final Contracts Updated

- `contracts/ci/ci-gate-contract.md` — schema-version bumped to 1.3.3; Phase 1e Gate Compatibility Notes section added documenting `tsconfig.json` include expansion to `src/resource-shared/**/*`.
- `contracts/CHANGELOG.md` — `[ci 1.3.3]` entry added.

## Final Tests Added / Updated

No new test files. Existing coverage:
- `frontend/tests/legacy/resource-status.test.js` — 244 assertions total across all legacy suites, all passed
- `npm run type-check` — 0 errors (tsconfig include expanded to 4 scopes)
- `npm run build` — exit 0 (Vite 11.20s)
- `npm run css:check` — 0 new violations

## Final CI/CD Gates

All Tier 1 gates passed (local + CI):
- frontend-unit, frontend-legacy, css-governance, frontend-build — PASSED (local)
- contract-validate, cdd-strict-gate, playwright-resilience, playwright-data-boundary, playwright-critical-journeys — PASSED (CI)
- frontend-type-check (informational) — PASSED

## Production Reality Findings

- No surprises. `ts-resolver-loader.mjs` handled specifier remapping in `resource-status.test.js` automatically; no test file changes needed after `.js → .ts` rename (confirmed by QA evidence).
- No `@ts-expect-error` needed: `resource-shared` imports only from already-migrated `core/` (Phase 1a), so no cross-phase suppression placeholders were required.
- QA confirmed 12/13 ACs passed locally; AC-13 (cdd-strict-gate) was pending CI and passed.

## Lessons Promoted to Standards

_(none — see below)_

## Follow-up Work

- `frontend-type-check` remains informational. Promotion to required follows the 20-day / 60-run Informational Gate Promotion Policy.
- Barrel available but consumers still import directly; future refactor can consolidate to index-based imports.
