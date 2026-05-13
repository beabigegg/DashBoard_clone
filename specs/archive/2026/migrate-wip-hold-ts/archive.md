---
change-id: migrate-wip-hold-ts
archived-date: 2026-05-13
archived-by: claude-main
---

# Archive — migrate-wip-hold-ts

## Change Summary

Phase 3 TypeScript migration of four Vue 3 feature apps: `wip-overview`, `wip-detail`, `hold-overview`, and `hold-detail`. All four apps had `main.js` renamed to `main.ts` and every `.vue` file's `<script setup>` block gained `lang="ts"`. Type annotations, local interfaces, and typed composable calls were added throughout — no runtime behavior, API shape, CSS, or business logic was changed. The `tsconfig.json` `include` array was expanded with the four new paths, and `contracts/ci/ci-gate-contract.md` was bumped to schema-version 1.3.7 with a Gate Compatibility Note documenting the scope expansion.

## Final Behavior

- All four feature apps are TypeScript-strict. `vue-tsc --noEmit` runs clean with zero errors across the migrated surface.
- `frontend/src/wip-overview/`, `wip-detail/`, `hold-overview/`, `hold-detail/` are now fully type-checked on every PR (informational gate, same as prior Phase 3 modules).
- `index.html` files in all four apps retain `./main.js` entry references (unchanged per CLAUDE.md rule — Vite resolves `main.ts` at build time).

## Final Contracts Updated

| Contract | Change | Version |
|---|---|---|
| `contracts/ci/ci-gate-contract.md` | Gate Compatibility Note added for four-app tsconfig scope expansion | 1.3.6 → 1.3.7 |
| `contracts/CHANGELOG.md` | Entry `[ci 1.3.7] — 2026-05-13` added | — |

## Final Tests Added / Updated

No new tests added. Existing 270 Vitest tests (27 files) all pass without modification. Python parity tests verified to contain no stale `.js` references to the migrated app directories.

## Final CI/CD Gates

| Gate | Tier | Status |
|---|---|---|
| frontend-unit | 1 (required) | Passed locally (270/270) |
| css-governance | 1 (required) | Passed locally (0 violations) |
| contract-validate | 0 (required) | Passed locally |
| playwright-critical-journeys | 1 (required) | Passed locally |
| frontend-type-check | informational | Passed locally (0 errors, scope now includes 4 new apps) |

## Production Reality Findings

No surprises. The change confirmed all existing Phase 3 migration patterns from `migrate-reject-history-ts` and `migrate-hold-history-ts`:
- echarts callbacks in `hold-overview/HoldTreeMap.vue` required 3 logical `TODO: type echarts callback` sites (tooltip formatter, label formatter, click handler) — expected and documented.
- No barrel completeness issues (wip-shared and resource-shared barrels were not touched).
- No Python parity test impact (none of the four apps had parity test references).

## Lessons Promoted to Standards

*None* — all patterns encountered in this change (echarts TODO annotation, drop-extension imports, index.html rule, tsconfig scope expansion with CI contract note) were already documented in CLAUDE.md from the prior Phase 3 migrations (`migrate-reject-history-ts`, `migrate-hold-history-ts`). This change is confirmatory evidence, not a new discovery.

## Follow-up Work

- **echarts callback typing** (deferred): `params: any` remains in HoldTreeMap.vue. Upstream @types/echarts lacks precise callback types. Can be addressed if echarts-specific typing is added in a future phase.
- **Informational gate promotion**: `frontend-type-check` becomes a candidate for promotion to required after 20 calendar days / 60 runs per the Informational Gate Promotion Policy.
- **Remaining TypeScript migration**: Feature apps not yet migrated (see `ts-migration-plan.md` for the remaining scope). This change closes the wip-overview / wip-detail / hold-overview / hold-detail batch.

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/` and active project guidance (`CLAUDE.md`, `CODEX.md`).
