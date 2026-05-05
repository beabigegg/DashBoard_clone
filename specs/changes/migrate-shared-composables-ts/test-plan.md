---
change-id: migrate-shared-composables-ts
schema-version: 0.1.0
last-changed: 2026-05-05
risk: medium
tier: 1
---

# Test Plan: migrate-shared-composables-ts

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 (all .js → .ts with explicit type annotations) | compile/contract | `cd frontend && npm run type-check` | 0 |
| AC-2 (index.ts provides typed re-exports) | compile/contract | `cd frontend && npm run type-check` | 0 |
| AC-3 (tsconfig include covers shared-composables) | compile/contract | `cd frontend && npm run type-check` | 0 |
| AC-4 (type-check exits 0, zero errors) | compile/contract | `cd frontend && npm run type-check` | 0 |
| AC-5 (existing Vitest suites pass) | unit | `frontend/tests/shared-composables/useAsyncJobPolling.test.js` | 0 |
| AC-5 (existing Vitest suites pass) | unit | `frontend/tests/shared-composables/useAutoRefresh.test.js` | 0 |
| AC-5 (existing Vitest suites pass) | unit | `frontend/tests/shared-composables/useRequestGuard.test.js` | 0 |
| AC-6 (consumer suites pass) | integration | `frontend/tests/abort/reject-history-abort.test.js` | 1 |
| AC-6 (consumer suites pass) | integration | `frontend/tests/abort/production-history-abort.test.js` | 1 |
| AC-6 (consumer suites pass) | integration | `frontend/tests/abort/query-tool-abort.test.js` | 1 |
| AC-6 (consumer suites pass) | integration | `frontend/tests/yield-alert/App.cross-filter.test.js` | 1 |
| AC-7 (no Python parity test refs deleted .js path) | audit/static | `grep -r "shared-composables.*\.js" tests/**/*.py` — zero hits required | 0 |
| AC-8 (build succeeds, same module surface) | build | `cd frontend && npm run build` | 1 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | Three existing `.test.js` suites (useAsyncJobPolling, useAutoRefresh, useRequestGuard) — kept `.test.js`; see policy below |
| compile/contract | 0 | `npm run type-check` (vue-tsc --noEmit); single command proves AC-1 through AC-4 |
| integration | 1 | Abort-scenario and cross-filter tests that import shared-composables by path; module path resolution after rename is the critical invariant |
| build | 1 | `npm run build` smoke — confirms Vite resolves `.ts` extensions and emits no missing-export errors |
| audit/static | 0 | One-shot grep of `tests/**/*.py` for `shared-composables/*.js`; expected zero matches (AC-7) |

## Test File Rename Policy

**Decision: keep all test files as `.test.js` — do not rename to `.test.ts`.**

Phase 1a precedent: `frontend/tests/core/api-dedup.test.js` remains `.js` even though `src/core/` is fully `.ts`. Vitest resolves `.ts` source imports from `.js` test files without configuration change. Renaming to `.ts` would require extending `tsconfig.json` include or toggling `allowJs` — that is Phase 1c scope, not this migration.

**Import specifier update is required (not a rename).** After source files move from `.js` to `.ts`, all test files referencing them with explicit `.js` extension must update those specifiers to `.ts` or drop the extension. This is a mechanical change verified by `npm run test` passing. Affected files:

- `frontend/tests/shared-composables/useAsyncJobPolling.test.js:13`
- `frontend/tests/shared-composables/useAutoRefresh.test.js:18`
- `frontend/tests/shared-composables/useRequestGuard.test.js:10`
- `frontend/tests/abort/production-history-abort.test.js:25,31`
- `frontend/tests/abort/reject-history-abort.test.js:49,70`
- `frontend/tests/abort/query-tool-abort.test.js:38,53`

## Out of Scope

- New unit tests for the 8 uncovered composables (useAutocomplete, usePaginationState, useQueryState, useUrlSync, useFilterOrchestrator, useAiChat, useSortableTable, useTraceProgress) — coverage gaps pre-exist this migration
- Renaming test files from `.test.js` to `.test.ts`
- Migrating `TraceProgressBar.vue` `<script>` block to `lang="ts"`
- E2E / Playwright tests (no runtime behavior change)
- Python parity test creation (shared-composables are not called by Python)
- Migrating feature-app-local composables

## Notes

- `tsconfig.json` has `"allowJs": false` and `"include": ["src/core/**/*"]`. Frontend-engineer adds `"src/shared-composables/**/*"` to `include` — no other tsconfig change required.
- `index.js` → `index.ts` rename also requires updating 8 internal re-export specifiers from `./useX.js` to `./useX.ts` (or extensionless).
- The abort consumer tests are the primary AC-6 evidence: a broken module path alias will cause Vitest module resolution failure, not just a type error, making them a stronger gate than type-check alone.
- Gate command sequence: `npm run type-check && npm run test && npm run build`.
