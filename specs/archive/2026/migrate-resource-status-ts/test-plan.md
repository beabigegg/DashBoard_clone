---
change-id: migrate-resource-status-ts
schema-version: 0.1.0
last-changed: 2026-05-13
risk: low
tier: 4
---

# Test Plan: migrate-resource-status-ts

## Acceptance Criteria → Test Mapping

| criterion id | test family   | test file path                                          | tier |
|---|---|---|---|
| AC-1         | compile-gate  | (npm run type-check — no file)                          | 4    |
| AC-2         | compile-gate  | (npm run type-check — zero errors)                      | 4    |
| AC-2         | unit          | frontend/tests/legacy/resource-status.test.js           | 4    |
| AC-2         | build-smoke   | (npm run build — exit 0)                                | 4    |
| AC-2         | css-gate      | (npm run css:check — exit 0)                            | 4    |
| AC-3         | compile-gate  | (npm run type-check — extension-drop verified via tsc)  | 4    |

## Test Families Required

- compile-gate (npm run type-check)
- unit (existing Vitest / node:test suite)
- build-smoke (npm run build)
- css-gate (npm run css:check)

Not required: contract, integration, e2e, data-boundary, resilience, monkey, stress, soak, visual.

## Test Family Details

### compile-gate

Command: `cd frontend && npm run type-check`

Expected result: exits 0 with zero TypeScript errors.

Covers:
- AC-1: confirms `main.ts` and all 7 SFCs compile cleanly with `<script setup lang="ts">`.
- AC-2: zero-error gate is the primary regression signal for this migration.
- AC-3: TypeScript resolves extension-less specifiers; any leftover `.js` import to a `.ts`
  source that the compiler cannot locate will surface as a compile error here.

No new test file needed — this is a CLI command gate, not a test suite.

### unit

File: `frontend/tests/legacy/resource-status.test.js`

Status: **no changes needed**. The file already uses static `import` (not `require()`), so it
is compatible with ES Module sources. It imports from `resource-shared/constants.js`; that
module is already TypeScript and the `.js` specifier is resolved correctly by Node + Vite.

Tests covered (one per logical assertion site):
- `normalizeStatus returns PRD for "PRD"`
- `normalizeStatus returns UDT for "PM" (aggregated)`
- `normalizeStatus returns EGT for "ENG" (aggregated)`
- `normalizeStatus returns NST for "OFF" (aggregated)`
- (remaining assertions in same file for `resolveOuBadgeClass`, `getStatusDisplay`,
  `STATUS_DISPLAY_MAP`, `STATUS_AGGREGATION`, `MATRIX_STATUS_COLUMNS`, `OU_BADGE_THRESHOLDS`)

Command: `cd frontend && npm run test`

### build-smoke

Command: `cd frontend && npm run build`

Expected result: exits 0; dist output includes resource-status bundle. Catches any runtime
import resolution failure that tsc alone might miss (e.g., dynamic import paths).

### css-gate

Command: `cd frontend && npm run css:check`

Expected result: exits 0. Confirms no CSS governance regression introduced by SFC changes.

## Out of Scope

- No new Vitest component tests — behavior is unchanged; existing unit suite is sufficient.
- No E2E or Playwright tests — Tier 4 refactor, no observable behavior change.
- No visual regression tests — layout is unchanged.
- No stress, soak, resilience, or monkey tests — not applicable to a TS rename.
- `index.html` is deliberately left referencing `./main.js`; no test needed to verify this
  (it is a pre-existing pattern across all feature apps; Vite resolves `main.ts` at build time).
- echarts `// TODO: type echarts callback` annotations are accepted placeholders; no test
  enforces their presence (audit is a code-review responsibility).

## Notes

- The single highest-value gate for this change is `npm run type-check`. Run it last after
  all SFCs are migrated so cascading errors from missing types are reported together.
- If `npm run type-check` fails on a specific SFC, fix type errors in that file before
  moving to the next; do not accumulate errors across files.
- `frontend/tests/legacy/resource-status.test.js` imports from `resource-shared/constants.js`
  (not `resource-status/`). It will not break regardless of changes inside `resource-status/`.
- No Python parity tests reference `resource-status/` source files; no Python test audit
  is required for this migration.
