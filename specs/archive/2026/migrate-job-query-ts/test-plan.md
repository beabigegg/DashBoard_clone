---
change-id: migrate-job-query-ts
schema-version: 0.1.0
last-changed: 2026-05-13
risk: low
tier: 3
---

# Test Plan: migrate-job-query-ts

Tier 3 TypeScript migration. No behaviour change. No API/data contracts touched.

---

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | test name / description | tier |
|---|---|---|---|---|
| AC-1 | type-check | `frontend/` (CI) | `npm run type-check` — `main.ts` DOM function params/returns resolve | type |
| AC-1 | build | `frontend/` (CI) | `npm run build` — Vite resolves `main.ts` while `index.html` retains `./main.js` | build |
| AC-2 | type-check | `frontend/` (CI) | `npm run type-check` — `UseJobQueryDataReturn` + `FiltersState` interfaces resolve | type |
| AC-3 | type-check | `frontend/` (CI) | `npm run type-check` — `App.vue` `<script setup lang="ts">` compiles; `formatCellValue(value: unknown): string` and `ExpandTxnLoader` props typed | type |
| AC-4 | type-check | `frontend/` (CI) | `npm run type-check` — no stale `.js` specifiers (TS cannot resolve them) | type |
| AC-5 | type-check | `frontend/` (CI) | `npm run type-check` — `tsconfig.json` include covers `src/job-query/**/*` | type |
| AC-6 | contract | `contracts/ci-gate-contract.md` + `contracts/CHANGELOG.md` | schema-version field reads `1.3.11`; CHANGELOG contains `[ci 1.3.11]` entry | contract |
| AC-7 | build / type-check / css | `frontend/` (CI) | `npm run build` exits 0; `npm run type-check` exits 0; `npm run css:check` exits 0 | build |
| AC-8 | unit (existing, unmodified) | `frontend/tests/legacy/portal-shell-parity-table-chart-matrix.test.js` | "Wave B native pages keep deterministic column and empty-state handling" — `/jobsColumns/`, `/txnColumns/`, `/目前無資料/` pass unchanged | unit |
| AC-8 | unit (full suite) | `frontend/tests/` | `npm run test` — zero regressions across all Vitest tests | unit |
| AC-9 | qa-review (manual) | `frontend/src/job-query/` | Auditor confirms no bare `any` without `// TODO: type <reason>`; no new `@ts-expect-error` | qa |
| AC-10 | gate | `specs/changes/migrate-job-query-ts/` | `cdd-kit gate migrate-job-query-ts --strict` exits 0 | gate |

---

## Test Families Required

type-check / build / contract / unit / qa-review / gate

Not exercised: integration / e2e / data-boundary / resilience / monkey / stress / soak — this change carries no behaviour delta.

---

## Out of Scope

| What | Why |
|---|---|
| Python parity tests (`test_frontend_*_parity.py`) | `change-classification.md` confirms no Python test references `job-query/main.js` or `useJobQueryData.js` |
| Visual / screenshot regression | No template markup is changed |
| API contract tests | No route, endpoint, or response schema is touched |
| `index.html` update test | Intentionally left unchanged per CLAUDE.md rule; `npm run build` exit-0 is sufficient proof |
| New Vitest unit tests for migrated files | No logic added or removed; type-check covers all new type assertions |

---

## Existing Test Audit

### `portal-shell-parity-table-chart-matrix.test.js` (lines 14–25)

Reads `src/job-query/App.vue` via `readSource()` and asserts `/jobsColumns/`, `/txnColumns/`, `/目前無資料/`.
All three patterns target the `<template>` section, which is not altered by this migration.
**No modification required.**

### Full Vitest suite

No other test file imports from `src/job-query/`. Run `npm run test` post-migration; no test files need editing.
