---
change-id: migrate-mid-section-defect-ts
schema-version: 0.1.0
last-changed: 2026-05-18
risk: low
tier: 0
---

# Test Plan: migrate-mid-section-defect-ts

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | test name / command | tier | notes |
|---|---|---|---|---|---|
| AC-1 | unit | `frontend/tests/legacy/mid-section-defect-composables.test.js` | all 8 node:test cases pass | 0 | inlines logic; no import of renamed app files; no repair expected |
| AC-1 | unit | `frontend/tests/legacy/msd-completeness-warning.test.js` | all 6 node:test cases pass | 0 | same pattern; static imports only |
| AC-2 | lint/type-check | n/a — CLI gate | `npm run type-check` exits 0 | 0 | vue-tsc; `tsconfig.json include` must cover `mid-section-defect` |
| AC-3 | unit | `frontend/tests/legacy/mid-section-defect-composables.test.js` | `npm run test` exits 0 | 0 | no `require()` or dynamic `.js` import found; no conversion needed |
| AC-3 | unit | `frontend/tests/legacy/msd-completeness-warning.test.js` | `npm run test` exits 0 | 0 | same |
| AC-4 | integration | `tests/e2e/test_mid_section_defect_e2e.py` | `pytest tests/e2e/test_mid_section_defect_e2e.py` exits 0 | 1 | no `.js` path refs found; audit still required before merge |
| AC-4 | lint (audit) | `tests/**/*.py` | `grep -r "mid-section-defect.*\.js" tests/` returns empty | 0 | pre-merge mandatory check |
| AC-5 | contract | `contracts/ci/ci-gate-contract.md` | `cdd-kit validate` exits 0; version == 1.3.14 | 0 | must include `### frontend-type-check scope expansion` note |
| AC-5 | contract | `contracts/CHANGELOG.md` | `cdd-kit validate` exits 0; entry for 1.3.14 present | 0 | matching entry required in same PR |
| AC-6 | lint (audit) | `frontend/src/shared-ui/components/MultiSelect.vue` | grep audit — no prop/emit removed or signature-broken | 0 | any additions must be additive; no new Vitest test required if surface unchanged |
| AC-7 | lint/type-check | `frontend/src/mid-section-defect/` (all `.ts`) | `npm run type-check` + audit: no `import('...file.js')` for renamed files | 0 | `vi.mock('...file.js')` static specifiers must NOT be updated |
| AC-8 | lint (audit) | `frontend/src/mid-section-defect/index.html` | `git diff HEAD -- frontend/src/mid-section-defect/index.html` shows no change | 0 | `./main.js` entry must remain unmodified |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | Vitest + node:test legacy files; pre-merge gate via `npm run test` |
| lint / type-check | 0 | `npm run type-check` (vue-tsc) + `npm run css:check`; pre-merge gate |
| contract | 0 | `cdd-kit validate`; covers AC-5 ci-gate-contract version bump |
| integration | 1 | `pytest tests/e2e/test_mid_section_defect_e2e.py` (mock-integration mode, no live Oracle); pre-merge gate |
| e2e | 3 | same file with `@pytest.mark.e2e`; requires live Oracle + Redis; nightly only |

## Gate Commands (must all pass pre-merge)

```
npm run type-check
npm run test
npm run css:check
pytest tests/ -m "not e2e"
cdd-kit validate
grep -r "mid-section-defect.*\.js" tests/    # must return empty
```

## Out of Scope

- No new Vitest or pytest test files: existing tests cover all AC after path audit.
- No parity tests (Node subprocess invoking `.ts` directly): no Python parity test for this app found.
- No visual / snapshot tests: zero UI output change.
- Stress (`tests/stress/test_mid_section_defect_stress.py`) — not a pre-merge gate; must not be broken.
- Monkey, soak, data-boundary, resilience families: out of scope for a pure type-migration.

## Notes

- Both legacy test files inline the production logic rather than importing from the app source; they survive the `.js→.ts` rename with no changes (AC-3 is a no-op audit).
- The E2E file contains no hardcoded `.js` path references; AC-4 audit is expected to be a no-op but must be confirmed by grep before merge.
- `vi.mock('...file.js')` specifiers must NOT be updated after rename (CLAUDE.md rule); enforcement is grep-audit only, not a new test case.
