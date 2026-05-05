# Change Request

## Original Request

TypeScript Phase 1b：將 `frontend/src/shared-composables/` 下的所有 `.js` 檔案遷移至 `.ts`，為所有 feature app 的 composable 呼叫建立型別契約。

Affected surface: `frontend/src/shared-composables/` (11 .js files + index.js)
Desired behavior: rename *.js → *.ts, add TypeScript type signatures to all composable parameters and return values
Success criterion: `cd frontend && npm run type-check` passes with zero errors for shared-composables; existing Vitest tests in `frontend/tests/shared-composables/` continue passing; feature apps importing from shared-composables compile without type errors

## Business / User Goal

Establish a typed contract at the composable layer so feature apps can import shared-composables with full IDE type inference and catch misuse at compile time rather than runtime.  This is Phase 1b of the incremental TypeScript migration (Phase 1a: core/ — complete).

## Non-goals

- Not migrating feature-app-local composables (e.g. `hold-history/useAutoRefresh.js`)
- Not migrating `shared-ui/` components (Phase 1c)
- Not adding new composable functionality

## Constraints

- Must follow CLAUDE.md TypeScript Migration Rules:
  - `node --experimental-strip-types` is used for parity tests (Node ≥22.6)
  - Audit Python tests in `tests/**/*.py` for any hardcoded `.js` paths referencing shared-composables
  - `frontend/tsconfig.json` must include shared-composables in its path
- Existing test files in `frontend/tests/shared-composables/` are `.js` — may need `.test.ts` rename or allowJs coverage
- `index.js` re-exports — update to `index.ts` with typed re-exports

## Known Context

- Phase 1a (`frontend/src/core/`) is complete: all 21 modules are `.ts`
- shared-composables is imported by multiple feature apps (wip, hold, query-tool, etc.)
- Three composables already have Vitest tests: useAsyncJobPolling, useAutoRefresh, useRequestGuard
- `frontend/tsconfig.json` currently scopes `include` to `core/**/*` for Phase 1a

## Open Questions

- Should test files in `frontend/tests/shared-composables/` be renamed to `.test.ts` simultaneously, or kept `.js` with `allowJs`?

## Requested Delivery Date / Priority

Priority: Normal (unblocked, follows Phase 1a completion)
