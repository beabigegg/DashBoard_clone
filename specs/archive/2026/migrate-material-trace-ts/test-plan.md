---
change-id: migrate-material-trace-ts
schema-version: 0.1.0
last-changed: 2026-05-18
risk: low
tier: 0
---

# Test Plan: migrate-material-trace-ts

## Acceptance Criteria — Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 (main.js → main.ts, no behavior change) | unit | `frontend/tests/legacy/material-trace-composables.test.js` | 0 |
| AC-2 (App.vue `<script setup lang="ts">`, no banned `as any`) | type | `npm run type-check` (vue-tsc --noEmit) | 0 |
| AC-3 (import specifiers drop .js extension) | type | `npm run type-check` (compile-time resolution check) | 0 |
| AC-4 (index.html still references `./main.js`, unmodified) | static | PR diff review — no `index.html` hunk | 0 |
| AC-5 (type-check passes, zero new errors) | type | `cd frontend && npm run type-check` | 0 |
| AC-6 (build succeeds, material-trace bundle produced) | build | `cd frontend && npm run build` | 1 |
| AC-7 (both existing test files continue to pass) | unit / contract | `cd frontend && npm run test` + `npm run test:legacy` | 0 |
| AC-8 (css:check passes) | lint | `cd frontend && npm run css:check` | 0 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit (node:test) | 0 | `material-trace-composables.test.js` — imports only from `core/`; survives rename untouched |
| contract (Vitest) | 0 | `useMaterialTrace.validation.test.js` — validates `/api/material-trace/spool` and `/api/material-trace/query` schemas; imports only `core/` modules |
| type | 0 | `npm run type-check` is the primary gate for AC-2, AC-3, AC-5 |
| build | 1 | `npm run build` must produce `dist/material-trace.html`; proves Vite resolves `main.ts` via `index.html ./main.js` reference |
| lint | 0 | `npm run css:check` for AC-8; no Python changes so ruff/mypy unaffected |
| e2e | 3 (nightly) | `tests/e2e/test_material_trace_e2e.py` — browser-driven, independent of source extensions; nightly only, not a PR gate |

## Tests That Must Fail Before Implementation

- `npm run type-check` — fails if `App.vue` lacks `lang="ts"` or has unresolved TS types introduced during migration.
- `npm run test:legacy` — fails if `node --experimental-strip-types` runner cannot resolve the import chain (catches silent extension-mismatch regressions).

## Out of Scope

- No new test files; this migration adds no new behavior.
- SFC-paired `*.test.ts` file: not expected; `vitest.config.js` `src/**/*.test.ts` pattern is already present if ever needed.
- Backend Python tests: no Python files change.
- E2E `test_material_trace_e2e.py`: deferred to nightly Tier 3 — rename-only change does not warrant PR-blocking browser tests.
- Property-based, resilience, stress, soak: out of scope for a TS rename migration.

## Notes

- `vitest.config.js` already includes `src/**/*.test.ts` (line 10); no config change needed for this migration.
- `npm run test:legacy` requires Node ≥22.6 (`--experimental-strip-types`); CI must use `setup-node@v4 / node-version: "22"`.
- AC-4 is verified by PR diff review (no `index.html` hunk), not by an automated test — this is the intentional Vite `main.js` → `main.ts` resolution pattern shared by all feature apps.
