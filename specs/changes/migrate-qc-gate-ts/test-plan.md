---
change-id: migrate-qc-gate-ts
schema-version: 0.1.0
last-changed: 2026-05-13
risk: low
tier: 3
---

# Test Plan: migrate-qc-gate-ts

Tier 3 TS-only refactor. No runtime behavior change. Coverage strategy: type-check gate proves
annotation correctness; existing Vitest suite proves behavior preservation; css:check and build
prove no CSS/bundler regression.

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file / command | tier |
|---|---|---|---|
| AC-1 | contract | `npm run type-check` (tsconfig include covers main.ts); verify `index.html` unchanged | static |
| AC-2 | contract | `npm run type-check`; grep for bare `any` without `// TODO:` in `useQcGateData.ts` | static |
| AC-3 | contract | `npm run type-check`; grep for stale `.js` import specifiers in `App.vue` | static |
| AC-4 | contract | `npm run type-check` (typed `defineProps` in `LotTable.vue`) | static |
| AC-5 | contract | `npm run type-check`; grep for `// TODO: type echarts callback` in `QcGateChart.vue` | static |
| AC-6 | contract | `grep -rn "from '.*\.js'" frontend/src/qc-gate/` must return no matches | static |
| AC-7 | contract | `grep "src/qc-gate" frontend/tsconfig.json` exits 0 | static |
| AC-8 | contract | `grep "1.3.8" contracts/ci/ci-gate-contract.md contracts/CHANGELOG.md` exits 0 | static |
| AC-9 | CI gate | `npm run type-check && npm run build && npm run css:check && npm run test` all exit 0 | CI gate |

## Test Families Required

contract / CI gate

## Out of Scope

- New Vitest unit tests: not required — pure rename; no new logic introduced.
- E2E / Playwright: `tests/e2e/test_qc_gate_e2e.py` is a read-only regression guard; no modification needed.
- Backend tests: `qc_gate_routes.py` / `qc_gate_service.py` are unaffected.
- Visual regression: no UI change.
- `style.css`: excluded from migration scope (no TypeScript content).
- Python parity tests: no `qc-gate` paths in `tests/test_frontend_*_parity.py`; no changes required.
- API / CSS / env contracts: no changes to API surface, class names, or env vars.

## Notes

Behavior preservation is guaranteed by the existing `npm run test` suite exiting 0 — no new test
files are created for this change. The `// TODO: type echarts callback` annotation on the
`handleChartClick` `params` parameter in `QcGateChart.vue` is the sole intentional `TODO` and
does not require a `// TODO:` justification for an `any` type (it is an unannotated parameter,
not a bare `any` cast). No Python test changes are required.
