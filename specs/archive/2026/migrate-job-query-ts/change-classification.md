# Change Classification

## Change Types
- primary: TypeScript migration (rename .js → .ts, add `lang="ts"` to SFC script setup)
- secondary: drop all stale `.js` import specifiers within migrated files, add typed interfaces for composable return shape and App.vue inline component props, expand `tsconfig.json` include to cover `src/job-query/**/*`

## Risk Level
- low

## Impact Radius
- module-level (`job-query/` source files only; shared layers are read-only reference targets; no behaviour change)

## Tier
- 3

## Architecture Review Required
- no

## Required Artifacts
Always required: change-request.md, change-classification.md, test-plan.md, ci-gates.md, tasks.yml

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | |
| proposal.md | no | |
| spec.md | no | |
| design.md | no | |
| qa-report.md | yes | release readiness evidence; per-AC typing audit record warrants explicit sign-off (consistent with prior Phase 3 migrations) |
| regression-report.md | no | |

## Required Contracts
- API: none
- CSS/UI: css-contract.md — confirm no new violations (style.css not modified)
- Env: none
- Data shape: none
- Business logic: none
- CI/CD: ci-gate-contract.md — schema-version bump 1.3.10 → 1.3.11 + frontend-type-check scope expansion note for `src/job-query/**/*`; contracts/CHANGELOG.md entry [ci 1.3.11]

## Required Tests
- unit: existing Vitest suite must pass with zero regressions
- contract: `css:check` must exit 0; `npm run type-check` must exit 0
- integration: none
- E2E: none
- visual: none
- data-boundary: none
- resilience: none
- fuzz/monkey: none
- stress: none
- soak: none

## Required Agents
- contract-reviewer
- test-strategist
- frontend-engineer
- ci-cd-gatekeeper
- qa-reviewer

## Inferred Acceptance Criteria
- AC-1: `main.js` → `main.ts`; all imports from `../core/*.js` drop the `.js` specifier; explicit types added to all DOM-manipulation function parameters and return values; `index.html` entry point left unchanged (Vite resolves `main.ts` at build time per CLAUDE.md rule)
- AC-2: `composables/useJobQueryData.js` → `useJobQueryData.ts`; a `UseJobQueryDataReturn` interface (or equivalent named type) is declared covering all returned refs, reactive state, and functions; `apiGet`/`apiPost` imports drop `.js` specifiers; `filters` reactive object typed with an explicit `FiltersState` interface (`{ resourceIds: string[]; startDate: string; endDate: string; searchText: string }`)
- AC-3: `App.vue` uses `<script setup lang="ts">`; import of `useJobQueryData.js` replaced with extension-free specifier; `ExpandTxnLoader` renderless component props typed with an inline interface; `formatCellValue` signature typed as `(value: unknown): string`
- AC-4: No stale `.js` specifiers remain in any migrated file; all internal imports use extension-free specifiers (per CLAUDE.md TypeScript Migration Rules)
- AC-5: `tsconfig.json` `include` array expanded with `"src/job-query/**/*"`
- AC-6: `ci-gate-contract.md` schema-version 1.3.11; `contracts/CHANGELOG.md` [ci 1.3.11] entry added documenting Phase 3 scope expansion for `job-query`
- AC-7: `npm run type-check` exits 0; `npm run build` exits 0; `css:check` exits 0
- AC-8: All existing Vitest tests pass (no regressions); `portal-shell-parity-table-chart-matrix.test.js` assertions against `App.vue` (`/jobsColumns/`, `/txnColumns/`, `/目前無資料/`) continue to pass unchanged
- AC-9: No bare `any` without `// TODO: type <reason>`; no new `@ts-expect-error` introduced (all `core/` deps are already `.ts`, so no cross-phase wrapper workarounds are needed)
- AC-10: `cdd-kit gate --strict` passes

## Tasks Not Applicable
- not-applicable: 2.1, 2.3, 2.4, 2.5, 3.2, 3.3, 3.4, 3.5, 4.1, 4.3, 5.1, 5.2, 6.4

## Clarifications or Assumptions
- `main.js` is a standalone DOM-manipulation script not imported by any Vue file; renaming it to `main.ts` has no downstream effect on `useJobQueryData.ts` or `App.vue`.
- `index.html` references `./main.js` — do NOT update; Vite resolves `main.ts` correctly at build time (per CLAUDE.md TypeScript Migration Rules).
- All declared dependencies (`../core/*.ts`, `../../core/api.ts`, `../shared-ui/components/*.vue`) are already fully TypeScript — no `@ts-expect-error` + cast pattern is needed.
- `style.css` is excluded from migration scope (no TypeScript content).
- No Python parity test files reference `job-query/main.js` or `useJobQueryData.js`; no Python test changes are required.
- The legacy test `portal-shell-parity-table-chart-matrix.test.js:15` reads `src/job-query/App.vue` using regex patterns (`/jobsColumns/`, `/txnColumns/`, `/目前無資料/`) that are template-level and survive a `<script>` block migration without modification.
- Route string references to `/job-query` in portal-shell tests are string constants, not file import paths, and are unaffected by this migration.
- `tsconfig.json` `include` currently ends at `"src/resource-history/**/*"` — `"src/job-query/**/*"` must be appended.
