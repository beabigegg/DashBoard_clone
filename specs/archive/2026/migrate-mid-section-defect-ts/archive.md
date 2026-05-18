---
change-id: migrate-mid-section-defect-ts
closed: 2026-05-18
---

# Archive: migrate-mid-section-defect-ts

## Change Summary

Phase 3 TypeScript migration of `frontend/src/mid-section-defect/`. Renamed `main.js → main.ts`, migrated `App.vue` to `<script setup lang="ts">` with full type annotations across all reactive state and helper functions, dropped `.js` extensions from 5 cross-feature import specifiers (4 in `App.vue`, 1 in `SuspectContextPanel.vue`), expanded `frontend/tsconfig.json` `include` with `"src/mid-section-defect/**/*"`, and bumped `contracts/ci/ci-gate-contract.md` 1.3.13 → 1.3.14 with matching `contracts/CHANGELOG.md` entry. No behavior, UI, or API surface changes.

## Final Behavior

`vue-tsc --noEmit` now type-checks `main.ts` and `App.vue` under `strict: true`. All 8 acceptance criteria pass. The 7 keep-as-is `.vue` sub-components remain untyped and are suppressed via `@ts-expect-error <phase note>` on import lines per the Phase 3 in-progress pattern.

## Final Contracts Updated

- `contracts/ci/ci-gate-contract.md`: schema-version 1.3.13 → 1.3.14; appended `### frontend-type-check scope expansion (Phase 3 — migrate-mid-section-defect-ts)` subsection.
- `contracts/CHANGELOG.md`: prepended `## [ci 1.3.14] — 2026-05-18` entry.

## Final Tests Added / Updated

None added. Existing tests confirmed as-is:
- `frontend/tests/legacy/mid-section-defect-composables.test.js` — inline logic; no import of renamed files (AC-3 no-op)
- `frontend/tests/legacy/msd-completeness-warning.test.js` — same pattern
- `tests/e2e/test_mid_section_defect_e2e.py` — no `.js` path references (AC-4 audit no-op)

## Final CI/CD Gates

| gate | result |
|---|---|
| frontend-type-check (`vue-tsc --noEmit`) | exit 0 |
| frontend-unit-tests (`npm run test`) | 346 passed / 1 skipped |
| frontend-css-check (`npm run css:check`) | 0 new errors (6 pre-existing in shared-ui, unrelated) |
| backend-unit-tests (`pytest tests/ -m "not e2e"`) | exit 0 |
| cdd-validate | exit 0; ci-gate-contract.md == 1.3.14 |
| grep-js-audit | empty (AC-4 confirmed) |
| index.html no-change audit | zero diff (AC-8 confirmed) |
| MultiSelect no-change audit | zero diff (AC-6 confirmed) |

## Production Reality Findings

No surprises. The app had no `composables/`, `services/`, or `utils/` subdirectories, making scope narrower than `material-trace`. The `buildFilterParams` / `buildDetailParams` helpers use `Record<string,unknown>` return types to accommodate dynamic property assignment — this preserved runtime behavior without requiring refactoring. The `@ts-expect-error` pattern suppressed all 7 non-`lang="ts"` component imports cleanly.

## Lessons Promoted to Standards

- **CLAUDE.md `## TypeScript Migration Rules`**: removed `mid-section-defect` from the "Remaining JS apps" list. Evidence: `frontend/src/mid-section-defect/main.ts` exists; `npm run type-check` exits 0 with `tsconfig.json include` covering this app.

## Follow-up Work

- Remaining Phase 3 JS apps: `admin-dashboard`, `admin-performance`, `admin-user-usage-kpi`, `anomaly-overview`, `portal`, `portal-shell`, `tables`.
- Line 494 in `App.vue` contains a stale inline comment referencing a `.js` path — advisory only; does not affect type-checking or runtime.

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/` and active project guidance.
