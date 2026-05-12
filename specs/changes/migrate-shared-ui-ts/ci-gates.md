---
change: migrate-shared-ui-ts
written-by: ci-cd-gatekeeper
date: 2026-05-12
---

# CI/CD Gate Plan — migrate-shared-ui-ts (Phase 1c)

## Change Summary

Phase 1c TypeScript migration: 22 Vue SFCs in `frontend/src/shared-ui/` converted to
`lang="ts"`, `index.js` renamed to `index.ts`, `tsconfig.json` `include` expanded to
cover `src/shared-ui/**/*`. No behavior change.

## Pre-merge Gate Status

| gate | tier | required | workflow | command | status |
|---|---:|---:|---|---|---|
| frontend-type-check | 0/1 | informational | frontend-tests.yml | `npm run type-check` | passes (0 errors) |
| frontend-unit | 1 | yes | frontend-tests.yml | `npm test` | passes (270/270) |
| contract-validate | 0 | yes | contract-driven-gates.yml | `cdd-kit validate` | existing gate, unchanged |

## Phase 1c Scope Expansion

- **Before Phase 1c**: `tsconfig.json` `include` was `["src/core/**/*", "src/shared-composables/**/*"]`,
  covering 21 core modules and 11 shared-composable modules.
- **From Phase 1c onward**: `include` is `["src/core/**/*", "src/shared-composables/**/*", "src/shared-ui/**/*"]`,
  additionally covering all 22 shared-ui `.ts`/`.vue` modules under `strict: true`.
- **Status unchanged**: `frontend-type-check` remains **informational** (`continue-on-error: true`
  in `frontend-tests.yml:38`). Promotion follows the standard Informational Gate Promotion Policy.
- **No new gate command needed**: the same `npm run type-check` invocation now covers the expanded
  `include` glob automatically — no workflow edits required.
- **No gates removed**: gate inventory is identical to Phase 1b.

## Node 22 Requirement

`frontend-tests.yml` uses `actions/setup-node@v4` with `node-version: "22"` (line 27-29).
This satisfies the CLAUDE.md requirement for `--experimental-strip-types` used by Python
parity tests. No change needed.

## Workflow Files — Verification Only

| file | action | outcome |
|---|---|---|
| `.github/workflows/frontend-tests.yml` | read-only verify | type-check + Vitest gates confirmed wired; Node 22 confirmed |
| `.github/workflows/contract-driven-gates.yml` | read-only verify | contract-validate gate confirmed; stack-specific gates live in frontend-tests.yml |

No workflow files were edited for this change.

## Gate Trigger

All gates triggered on: PR open / push to branch. `frontend-unit` (Tier 1) blocks merge if failed. `frontend-type-check` (informational) does not block merge.

## Rollback Policy

If `npm run type-check` regresses after merge (e.g., downstream consumer introduces a type error exposed by the new `src/shared-ui/**/*` include):
1. Revert the specific SFC to `<script setup>` (remove `lang="ts"`)
2. Open a follow-up CDD change for that component
3. The rollback does not affect the other 21 migrated SFCs

No DB migrations, API changes, or data shape changes are in scope — rollback is limited to reverting `.vue` `lang` attribute and removing `defineProps<T>()` for the affected file only.

## Merge Eligibility

All Tier 1 required gates pass locally. `frontend-type-check` passes with 0 errors (informational gate — does not block merge regardless). This change is gate-ready.
