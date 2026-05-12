# Archive: migrate-reject-history-ts

**Cold Data Warning**: This archive is historical evidence. Current requirements live in `contracts/` and active project guidance.

---

## Change Summary

Migrated `frontend/src/reject-history/` (the highest-complexity Phase 3 feature app) from JavaScript to TypeScript. The app contains a 1370-line `App.vue`, a DuckDB composable for local Pareto analytics, and multi-dimensional filter logic. The migration is a pure rename + annotation pass with zero behavior changes, establishing the DuckDB typing pattern reusable by subsequent Phase 3 apps (`hold-history/`, `resource-history/`).

## Final Behavior

The system behaves identically before and after migration. All `.js` files under `src/reject-history/` are now `.ts` / `lang="ts"` SFCs. `tsconfig.json` includes `src/reject-history/**/*`. `npm run type-check` exits with 0 errors.

## Final Contracts Updated

- `contracts/ci/ci-gate-contract.md` — schema-version bumped to 1.3.5; Phase 3 note added (lines 71–76).

## Final Tests Added / Updated

- 270/270 Vitest tests pass (27 test files); 28 reject-history test cases included.
- No new tests were required; the existing suite provided sufficient coverage.

## Final CI/CD Gates

| gate | command | tier |
|---|---|---|
| frontend-type-check | `cd frontend && npm run type-check` | PR Required |
| frontend-unit | `cd frontend && npm run test` | PR Required |
| css-governance | `cd frontend && npm run css:check` | PR Required |
| playwright-critical-journeys | `npx playwright test tests/playwright/reject-history.spec.js` | Informational |
| python-parity-audit | `pytest test_frontend_compute_parity.py test_frontend_duckdb_parity.py` | Informational |

## Production Reality Findings

- **10 `TODO: type` annotations accepted**: 4 in App.vue (core/api not yet TS), 2 in TrendChart.vue + 2 in ParetoSection.vue (echarts callback gaps), 2 in useRejectHistoryDuckDB.ts (JS boundary + DOM cast). All acceptable pre-merge; resolve when core/api migrates.
- **index.html still references `./main.js`**: Vite resolves `main.ts` correctly at build time. Pre-existing cosmetic pattern across all feature apps; not worth fixing per-app.

## Lessons Promoted to Standards

1. **`index.html` entry point** → `CLAUDE.md` § TypeScript Migration Rules  
   `index.html` references `./main.js`; Vite resolves `main.ts` at build time. Do not update `index.html` during per-app Phase 3 migrations.  
   Evidence: `reject-history/index.html`, QA report AC-3 observation.

2. **echarts callback type gap** → `CLAUDE.md` § TypeScript Migration Rules  
   echarts callback params lack precise types. Annotate with `// TODO: type echarts callback`; do not block migration.  
   Evidence: `TrendChart.vue`, `ParetoSection.vue`; QA report TODO:type debt table.

## Follow-up Work

- Resolve 10 `TODO: type` annotations when `core/api` completes its TypeScript migration.
- Cosmetic: update `index.html` entry-point references from `main.js` → `main.ts` across all feature apps (low priority — Vite resolves both).
- Next Phase 3 app: `hold-history/` (DuckDB composable + Future Hold accumulation logic).
