---
change-id: migrate-wip-shared-ts
schema-version: 0.1.0
last-changed: 2026-05-12
risk: low
tier: 1
---

# Test Plan: migrate-wip-shared-ts

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 | type-check | `npm run type-check` (vue-tsc --noEmit) | 1 |
| AC-2 | type-check | `npm run type-check` (vue-tsc --noEmit) | 1 |
| AC-3 | type-check | `npm run type-check` (vue-tsc --noEmit) | 1 |
| AC-4 | type-check | `npm run type-check` (vue-tsc --noEmit) | 1 |
| AC-5 | type-check | `npm run type-check` (vue-tsc --noEmit) | 1 |
| AC-6 | type-check | `npm run type-check` (vue-tsc --noEmit) | 1 |
| AC-7 | type-check | `npm run type-check` (vue-tsc --noEmit) | 1 |
| AC-8 | type-check | `npm run type-check` exits 0 with suppressions removed | 1 |
| AC-9 | build | `npm run build` exits 0 (Vite resolves all specifiers) | 1 |
| AC-10 | type-check | `npm run type-check` covers wip-shared (tsconfig.json include verified) | 1 |
| AC-11 | contract | `cdd-kit validate` — ci-gate-contract.md schema-version 1.3.4 + CHANGELOG entry | 1 |
| AC-12 | build / type-check / css | `npm run type-check && npm run build && npm run css:check` all exit 0 | 1 |
| AC-13 | unit | `npm run test` — existing Vitest suite passes without regression | 1 |
| AC-14 | type-check | `npm run type-check` — grep confirms no `as any` and no new `@ts-expect-error` in wip-shared | 1 |
| AC-15 | contract | `cdd-kit gate migrate-wip-shared-ts --strict` exits 0 | 1 |

## Test Families Required

type-check, build, unit, contract

## Out of Scope

- Python parity tests: no Python test references wip-shared files.
- `loading-standardization.test.js`: reads styles.css only; unaffected by this migration.
- `portal-shell-wave-a-chart-lifecycle.test.js`: checks ParetoSection.vue path by filename; .vue extension unchanged.
- Integration/e2e/resilience/monkey/stress/soak: purely a TypeScript migration with no runtime logic changes.

## Notes

**@ts-expect-error removal (AC-8):** `shared-composables/useAutocomplete.ts`,
`useAutoRefresh.ts`, and `shared-ui/PaginationControl.vue` contain
`@ts-expect-error` suppressions that reference not-yet-migrated wip-shared
files. Removing these lines is the correct action once wip-shared is typed.
Validation: `npm run type-check` must exit 0 after removal — a compile error
would mean the suppression was still needed and the migration is incomplete.
