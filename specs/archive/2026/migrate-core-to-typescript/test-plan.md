---
change-id: migrate-core-to-typescript
schema-version: 0.1.0
last-changed: 2026-05-05
risk: medium
tier: 1
---

# Test Plan: migrate-core-to-typescript

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | test name / description | tier |
|---|---|---|---|---|
| AC-1 | unit (build-time) | `npm run type-check` (vue-tsc --noEmit) | No `.js` files remain in `src/core/` — verified by type-check scope widening + glob assertion | 0 |
| AC-2 | unit | `frontend/tests/unwrap-api-result.test.js` | `ApiResponse<T>` export reachable; existing unwrap tests still pass | 0 |
| AC-3 | unit | `frontend/tests/schema-guard.test.js` | All `assertShape` primitive / nested / array tests pass unchanged | 0 |
| AC-3 | unit (build-time) | `npm run type-check` | `endpoint-schemas.ts` TS interfaces compile with 0 errors | 0 |
| AC-4 | unit (build-time) | `npm run type-check` | `vue-tsc --noEmit` exits 0 after tsconfig `include` widened to `src/core/**/*` | 0 |
| AC-5 | unit | `frontend/tests/core/api-dedup.test.js` | All GET/POST dedup + size-tracking tests pass unchanged | 0 |
| AC-5 | unit | `frontend/tests/unwrap-api-result.test.js` | All `unwrapApiResult` / `unwrapApiData` tests pass unchanged | 0 |
| AC-5 | unit | `frontend/tests/schema-guard.test.js` | All `assertShape` tests pass unchanged | 0 |
| AC-5 | unit | `frontend/tests/legacy/datetime.test.js` | All `formatLogTime` tests pass unchanged | 0 |
| AC-5 | unit | `frontend/tests/legacy/wip-derive.test.js` | All `buildWipOverview/DetailQueryParams`, `splitHoldByType`, `prepareParetoData` tests pass | 0 |
| AC-5 | unit | `frontend/tests/legacy/*.test.js` (remaining 27 files) | Full legacy suite passes via `npm run test:legacy` | 0 |
| AC-5 | unit | `frontend/tests/pending-jobs-registry.test.js` | Passes unchanged | 0 |
| AC-6 | unit (build-time) | `npm run type-check` | Bare `any` without TODO comment causes `strict` type error — confirmed by 0-error exit | 0 |
| AC-7 | integration (build) | `npm run build` | Vite build succeeds; no missing-module or type-emit errors | 1 |
| AC-8 | unit (build-time) | `npm run type-check` | Downstream imports of `src/core/index.ts` barrel compile with 0 errors | 0 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | Vitest suite (`npm run test`) + Node test runner legacy suite (`npm run test:legacy`) — both must exit 0 |
| build-time (type-check) | 0 | `vue-tsc --noEmit` acts as a static-analysis gate, not a Vitest test; exit code 0 = pass |
| integration (build) | 1 | `npm run build` proves bundler resolves `.ts` imports end-to-end; required pre-merge |

## Out of Scope

- Backend tests (Python/pytest) — no backend changes in this migration.
- E2E / Playwright — no UI behavior changes; covered by AC-7 build gate.
- Contract tests — `contracts/api/api-contract.md` is unchanged; `ApiResponse<T>` is a static parallel layer only.
- Performance / soak / stress — rename-only migration, no algorithmic changes.
- New Vitest test files — all AC coverage comes from existing test files + build-time gates.

## Notes

`npm run type-check` (`vue-tsc --noEmit`) is a **build-time gate**, not a Vitest test. It must be run as a separate CI step; failure blocks merge independent of Vitest results.

AC-6 (no bare `any`) is enforced passively by `strict: true` in `tsconfig.json` — any untyped `any` that reaches a function boundary will surface as a type error in the type-check step.

Test files remain `.js`; only `frontend/src/core/` source files change extensions. Import paths in tests that use static `.js` extensions (e.g. `import ... from '../../src/core/api.js'`) will require Vite/Vitest resolver alignment — this is an implementer concern, not a test-plan concern.
