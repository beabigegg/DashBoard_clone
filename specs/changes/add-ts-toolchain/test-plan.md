---
change-id: add-ts-toolchain
schema-version: 0.1.0
last-changed: 2026-05-05
risk: low
tier: 1
---

# Test Plan: add-ts-toolchain

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path / command | tier |
|---|---|---|---|
| AC-1 | contract | smoke: `node -e "const p=require('./package.json'); ['typescript','vue-tsc','@types/node'].forEach(d=>{ if(!p.devDependencies[d]) process.exit(1) })"` in `frontend/` | 0 |
| AC-2 | contract | smoke: `node -e "const t=JSON.parse(require('fs').readFileSync('tsconfig.json')); if(!t.compilerOptions.strict||t.compilerOptions.allowJs!==false||!t.include.every(p=>p.startsWith('src/core/'))) process.exit(1)"` in `frontend/` | 0 |
| AC-3 | contract | smoke: `npm run type-check` exits 0 AND `frontend/vite.config.js` no longer exists AND `frontend/vite.config.ts` exists | 0 |
| AC-4 | contract | smoke: `cd frontend && npm run type-check`; assert exit code 0 | 0 |
| AC-5 | contract | smoke: inject synthetic TS error into `frontend/src/core/` stub file, run `npm run type-check`, assert exit code non-zero; revert | 1 |
| AC-6 | contract + regression | existing CI gate: `npm run test` (Vitest), `npm run test:legacy`, `npm run css:check` all exit 0 | 1 |
| AC-7 | contract | `cdd-kit validate` — `contracts/ci/ci-gate-contract.md` must contain `frontend-type-check` gate row | 0 |
| AC-8 | contract | smoke: `cdd-kit validate` exits 0 on clean checkout | 0 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| contract | 0 | `cdd-kit validate` confirms CI gate contract; JSON field checks for package.json and tsconfig.json |
| smoke (CLI) | 0 | Script-level exit-code checks run locally pre-PR; no new test files needed |
| regression | 1 | Existing Vitest + legacy node --test suites run unmodified in CI PR gate |

## Out of Scope

- Unit tests: no source code added; nothing to unit-test.
- Integration / E2E / data-boundary / resilience / stress / soak: not applicable to toolchain wiring.
- Visual regression: no UI changes.
- `npm run build` full production build: heavy; covered by existing nightly, not added here.
- Playwright suites: unchanged, continue running per their existing gate assignments.

## Notes

AC-5 (synthetic-error test) is a one-shot manual verification performed once by the implementing engineer before merge; it is not wired into automated CI (injecting then reverting a deliberate error in CI is fragile).

The `frontend-type-check` gate starts as `informational` per the contract; promotion to `required` follows the standard 20-day/60-run policy in `ci-gate-contract.md`.

No new test files are created by this change. All verification is via script exit codes and `cdd-kit validate`.
