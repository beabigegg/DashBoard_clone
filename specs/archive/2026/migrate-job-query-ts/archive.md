---
change-id: migrate-job-query-ts
archived: 2026-05-13
status: complete
---

# Archive — migrate-job-query-ts

## Change Summary

Migrated `frontend/src/job-query/` from JavaScript to TypeScript (Phase 3 of the incremental
frontend TS migration programme). Renamed `main.js` → `main.ts` and
`composables/useJobQueryData.js` → `useJobQueryData.ts`; added `lang="ts"` to `App.vue`
script block; declared `UseJobQueryDataReturn`, `FiltersState`, and `Resource` interfaces;
narrowed `getStatusTone` return to `'neutral' | 'success' | 'warning' | 'danger'` to satisfy
`StatusBadge` prop union; dropped all `.js` import specifiers; expanded `tsconfig.json`
include to cover `src/job-query/**/*`; bumped `ci-gate-contract.md` schema-version to 1.3.11.
No behaviour change — pure type annotation pass.

## Final Behavior

- `frontend/src/job-query/main.ts` — standalone DOM-manipulation script; all function
  parameters and return types annotated; portal-shell globals declared via `declare const`.
- `frontend/src/job-query/composables/useJobQueryData.ts` — composable with named
  `UseJobQueryDataReturn` interface covering all 21 exported refs/functions/state;
  `FiltersState` and `Resource` interfaces exported.
- `frontend/src/job-query/App.vue` — `<script setup lang="ts">`; `ExpandTxnLoader` props
  typed; `formatCellValue(value: unknown): string` typed.
- `frontend/tsconfig.json` now covers `src/job-query/**/*` under `strict: true`.

## Final Contracts Updated

| contract | version | nature |
|---|---|---|
| `contracts/ci/ci-gate-contract.md` | 1.3.11 | Additive: `frontend-type-check` scope expansion note for `src/job-query/**/*` |
| `contracts/CHANGELOG.md` | — | New entry `[ci 1.3.11]` — 2026-05-13 |

## Final Tests Added / Updated

| file | change |
|---|---|
| `tests/test_job_query_frontend_safety.py` | Path updated: `main.js` → `main.ts` (CI fix) |
| `frontend/tests/legacy/portal-shell-parity-table-chart-matrix.test.js` | No change required — regex patterns target `<template>` section only |

No new Vitest unit tests added (no logic change).

## Final CI/CD Gates

| gate | status | result |
|---|---|---|
| frontend-unit (`npm run test`) | PR-blocking | 302/302 passed, 0 regressions |
| css-governance (`npm run css:check`) | PR-blocking | 0 violations |
| frontend-type-check (`npm run type-check`) | informational | 0 errors |
| contract-validate (`cdd-kit validate`) | local pre-PR | passed |
| cdd-kit gate --strict | local pre-PR | passed |
| released-pages-hardening (CI) | required | passed after safety-test path fix |

## Production Reality Findings

**Missed Python path reference (CI failure):** `tests/test_job_query_frontend_safety.py:15`
used `pathlib.Path` to read `frontend/src/job-query/main.js` directly. After renaming to
`main.ts`, the test raised `FileNotFoundError` in CI. The file was not in the change's
context manifest allowed paths — it was a static-analysis safety test, not a parity test,
and was not caught by the pre-flight context check.

Fix: one-line change (`main.js` → `main.ts`), committed as a follow-up.

Root cause: the CLAUDE.md audit rule mentions "parity tests" as the primary example for
Python tests that reference `.js` paths, while safety/static-analysis tests that read source
files via `pathlib` are equally affected but not called out explicitly.

## Lessons Promoted to Standards

| lesson | target | location | evidence |
|---|---|---|---|
| Python safety tests using `pathlib.Path.read_text()` on source files are equally affected by `.js → .ts` renames as parity tests — audit both classes | `CLAUDE.md` | TypeScript Migration Rules bullet 2 — sentence appended | `tests/test_job_query_frontend_safety.py:15` |

## Follow-up Work

- `frontend-type-check` remains informational; promotion to required is deferred until all
  Phase 3 feature-app migrations complete and gate holds clean for two release cycles.
- No other known issues.

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/` and active
project guidance (`CLAUDE.md`).
