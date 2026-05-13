---
change-id: migrate-resource-history-ts
schema-version: 0.1.0
last-changed: 2026-05-13
risk: low
tier: 4
---

# Test Plan: migrate-resource-history-ts

Tier 4 TS-only refactor. No runtime behavior change. Coverage strategy: type-check gate proves
annotation correctness; existing Vitest suite proves behavior preservation; legacy node:test proves
OEE formula contract; css:check and build prove no CSS/bundler regression.

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file / command | tier |
|---|---|---|---|
| AC-1 | contract | `npm run type-check` (tsconfig include covers main.ts); verify `index.html` unchanged (`grep './main.js' frontend/src/resource-history/index.html` exits 0) | static |
| AC-2 | contract | `npm run type-check`; grep for bare `any` without `// TODO:` in `useResourceHistoryDuckDB.ts` | static |
| AC-3 | contract | `npm run type-check`; grep for stale `.js` import specifiers in `App.vue` | static |
| AC-4 | contract | `npm run type-check` (typed `defineProps` / `defineEmits` in `FilterBar.vue`) | static |
| AC-5 | contract | `npm run type-check` (typed `defineProps` with `ResourceKpi` in `KpiCards.vue`) | static |
| AC-6 | contract | `npm run type-check`; grep for `// TODO: type echarts callback` in each of `TrendChart.vue`, `StackedChart.vue`, `ComparisonChart.vue`, `HeatmapChart.vue` | static |
| AC-7 | contract | `npm run type-check`; grep for `// TODO: type hierarchy node union` in `DetailSection.vue` | static |
| AC-8 | contract | `grep -rn "from '.*\.js'" frontend/src/resource-history/` must return no matches | static |
| AC-9 | contract | `grep "src/resource-history" frontend/tsconfig.json` exits 0; confirm it is the 15th entry in the include array | static |
| AC-10 | contract | `grep "1.3.9" contracts/ci/ci-gate-contract.md contracts/CHANGELOG.md` exits 0 | static |
| AC-11 | CI gate | `npm run type-check && npm run build && npm run css:check && npm run test` all exit 0 | CI gate |
| AC-12 | unit | `node --test frontend/tests/legacy/resource-history.test.js` exits 0; file diff shows no changes to the test source | static |

## Test Families Required

contract / unit / CI gate

## Out of Scope

- New Vitest unit tests: not required — pure rename; no new logic introduced.
- E2E / Playwright: no resource-history E2E suite exists; no modification needed.
- Backend tests: `resource_history_routes.py` / `resource_history_service.py` are unaffected.
- Visual regression: no UI change.
- `style.css`: excluded from migration scope (no TypeScript content).
- `index.html`: excluded from migration scope; `./main.js` reference is cosmetic pre-existing pattern.
- Python parity tests: no `resource-history` paths in `tests/test_frontend_*_parity.py`; no changes required.
- API / CSS / env contracts: no changes to API surface, class names, or env vars.
- Barrel audit: resource-history has no barrel `index.js`/`index.ts`; not applicable.

## Notes

`frontend/tests/legacy/resource-history.test.js` uses fully inline formula replicas (no imports from
source), so it passes unchanged after the `.js → .ts` rename. No regex updates are needed.

The `// TODO: type echarts callback` annotation applies to formatter/tooltip callback parameters in
the four chart components. The `// TODO: type hierarchy node union` annotation applies to `value(node)`
callbacks in `DetailSection.vue`. Both are counted as logical annotation sites per CLAUDE.md rules —
multiple physical comment lines at a single logical site are expected and not a discrepancy.

Behavior preservation is guaranteed by the existing `npm run test` (Vitest) suite exiting 0 — no new
test files are created for this change. No Python test changes are required.
