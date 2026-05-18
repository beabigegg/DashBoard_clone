# Archive — migrate-material-trace-ts

## Change Summary

Migrated the `material-trace` feature app from JavaScript to TypeScript as part of the
project-wide Phase 3 per-app TS migration. The two source files were updated:
`main.js` was renamed `main.ts` (no code changes), and `App.vue` gained
`<script setup lang="ts">` with full type annotations — local interfaces for
`Pagination`, `QualityMeta`, `MaterialTraceFilterOptions`, `MaterialTraceQueryPayload`,
and `MaterialTraceJobStatus`; typed `ref<T>()` calls; annotated function parameters;
`ReturnType<typeof setTimeout> | null` for the polling timer; template cast for the
`<select>` event; and `instanceof Error` narrowing in catch blocks. Import specifiers
dropped the `.js` extension per Phase 3 convention. `tsconfig.json` gained
`"src/material-trace/**/*"` in its `include` array, and `contracts/ci/ci-gate-contract.md`
was bumped from 1.3.12 → 1.3.13 with the scope expansion note.

## Final Behavior

No behavior change. The material-trace page renders identically; all runtime semantics
are unchanged. TypeScript now type-checks `main.ts` and `App.vue` under `strict: true`.

## Final Contracts Updated

| contract | change |
|---|---|
| `contracts/ci/ci-gate-contract.md` | schema-version 1.3.12 → 1.3.13; scope expansion note for `src/material-trace/**/*` |
| `contracts/CHANGELOG.md` | entry `[ci 1.3.13] — 2026-05-18` |

## Final Tests Added / Updated

No new test files. Existing anchors confirmed passing:
- `frontend/tests/legacy/material-trace-composables.test.js`
- `frontend/tests/validation/useMaterialTrace.validation.test.js`

All 8 acceptance criteria mapped in `test-plan.md`; no new test file required
(test-strategist agent-log confirms mapping completeness).

## Final CI/CD Gates

| gate | tier | status |
|---|---|---|
| frontend-type-check | 1 (informational) | passed locally + CI |
| frontend-build | 1 | passed locally + CI |
| frontend-unit | 1 | passed locally + CI |
| css-governance | 1 | passed locally + CI |
| material-trace-e2e | 2 (informational) | not blocking |

No workflow file changes. All gates already wired in `.github/workflows/frontend-tests.yml`
(ci-cd-gatekeeper agent-log confirms no new jobs needed).

## Production Reality Findings

No surprises. The migration followed the established Phase 3 pattern exactly. One
pre-existing finding noted during verification: `npm run css:check` reported 6
HEX-color violations in `query-tool/EquipmentRejectsTable.vue` — pre-existing,
unrelated to this change, exit code 0 (warning level only).

## Lessons Promoted to Standards

**L-1 → promote-to-guidance (CLAUDE.md §TypeScript Migration Rules)**
Every Phase 3 per-app migration must bump `contracts/ci/ci-gate-contract.md` (patch version) with a `### frontend-type-check scope expansion` note and a matching `contracts/CHANGELOG.md` entry. Evidence: 8 consecutive scope-expansion notes ci 1.3.1–1.3.13; `agent-log/ci-cd-gatekeeper.yml`.

**L-2 → do-not-promote**
`index.html` must not be modified during Phase 3 migrations — already present verbatim in CLAUDE.md §TypeScript Migration Rules.

**L-3 → promote-to-guidance (CLAUDE.md §CDD Kit Commands)**
Tasks 6.2/6.3 may be marked `done` before CI confirmation when local Tier 1 gates pass the same commands; task 6.4 marked `skipped` when no nightly/weekly/manual gates are defined. Leaving any section-6 task pending blocks the pre-commit hook. Evidence: `tasks.yml` lines 37-39.

**L-4 → do-not-promote**
`ReturnType<typeof setTimeout> | null` is a standard TypeScript idiom, not project-specific guidance.

## Follow-up Work

None. `material-trace` is now fully migrated. Remaining Phase 3 JS apps:
`admin-dashboard`, `admin-performance`, `admin-user-usage-kpi`, `anomaly-overview`,
`mid-section-defect`, `portal`, `portal-shell`, `tables`.

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/` and
active project guidance (`CLAUDE.md`/`CODEX.md`).
