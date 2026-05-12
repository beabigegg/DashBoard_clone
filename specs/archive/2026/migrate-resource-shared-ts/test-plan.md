---
change-id: migrate-resource-shared-ts
schema-version: 0.1.0
last-changed: 2026-05-12
risk: low
tier: 1
---

# Test Plan: migrate-resource-shared-ts

## Acceptance Criteria → Test Mapping

| criterion_id | test_family | test_file | test_name | tier |
|---|---|---|---|---|
| AC-1 | unit | frontend/tests/legacy/resource-status.test.js | all 35+ cases (normalizeStatus, resolveOuBadgeClass, getStatusDisplay, constants) | 1 |
| AC-2 | type-check | (vue-tsc gate) | HierarchyTable.vue defineProps generic syntax | 1 |
| AC-3 | type-check | (vue-tsc gate) | MultiSelect.vue defineProps generic syntax | 1 |
| AC-4 | type-check | (vue-tsc gate) | index.ts barrel — named imports resolve for 2 components + all constants | 1 |
| AC-5 | type-check | (vue-tsc gate) | consumers compile clean after extension-free specifier drop | 1 |
| AC-6 | type-check | (vue-tsc gate) | tsconfig.json include covers src/resource-shared/**/* | 1 |
| AC-7 | contract | contracts/CHANGELOG.md + ci-gate-contract.md | schema-version 1.3.3 entry present | 1 |
| AC-8 | type-check | (npm run type-check) | exits 0 across all migrated modules | 1 |
| AC-9 | build | (npm run build) | exits 0 | 1 |
| AC-10 | css | (npm run css:check) | exits 0 — 0 new violations | 1 |
| AC-11 | unit | frontend/tests/legacy/resource-status.test.js | 35+ legacy tests pass | 1 |
| AC-12 | type-check | (vue-tsc gate) | no `as any`; no `@ts-expect-error` in migrated files | 1 |
| AC-13 | contract | (cdd-kit gate --strict) | all gates pass | 1 |

## Test Families Required

unit, type-check, build, css, contract

## Out of Scope

- Python parity tests: no `resource-shared` path referenced in any `tests/**/*.py` file; no new parity test needed.
- New Vitest test files: the legacy suite already covers all constants and utility functions. No net-new test authoring is required for this change.
- E2E / resilience / stress / soak: pure rename/type migration with no runtime behavior change.

## Notes

`ts-resolver-loader.mjs` (configured in `frontend/vitest.config.js`) automatically remaps `.js` specifiers to `.ts` at test-load time. The existing import `../../src/resource-shared/constants.js` in `resource-status.test.js` therefore resolves correctly to `constants.ts` after the rename — the test file requires no modification to cover AC-1 and AC-11.

Type-check and build gates (AC-2 through AC-10, AC-12) are verified by CI commands rather than discrete test files. Pass/fail is binary: `vue-tsc --noEmit` and `vite build` must exit 0.
