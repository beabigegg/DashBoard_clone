# Change Classification

## Change Types
- primary: TypeScript migration (refactor)
- secondary: barrel audit/creation

## Risk Level
- low

## Impact Radius
- module-level

## Tier
- 3

## Architecture Review Required
- no

## Required Artifacts
Always required: change-request.md, change-classification.md, test-plan.md, ci-gates.md, tasks.yml

## Optional Artifacts
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | |
| proposal.md | no | |
| spec.md | no | |
| design.md | no | |
| qa-report.md | yes | Track per-file migration results and AC verification |
| regression-report.md | no | |

## Required Contracts
- API: none
- CSS/UI: contracts/css/css-contract.md, contracts/css/css-inventory.md (read-only; verify no path regressions)
- Env: none
- Data shape: none
- Business logic: none
- CI/CD: contracts/ci/ci-gate-contract.md (verify type-check/Vitest gates cover .ts files)

## Required Tests
- unit: frontend/tests/legacy/admin-dashboard.test.js, admin-performance.test.js, admin-user-usage-kpi.test.js
- contract: cd frontend && npm run type-check
- integration: cd frontend && npm run build
- E2E: none
- visual: none
- data-boundary: none
- resilience: none
- fuzz/monkey: none
- stress: none
- soak: none

## Required Agents
- contract-reviewer
- test-strategist
- frontend-engineer
- ci-cd-gatekeeper
- qa-reviewer

## Inferred Acceptance Criteria
- AC-1: All `.js` source files under `frontend/src/admin-shared/` are renamed to `.ts` with valid type annotations (no implicit `any`).
- AC-2: All Vue SFCs under `frontend/src/admin-shared/components/` use `<script lang="ts">` with typed `defineProps`/`defineEmits` where applicable.
- AC-3: `cd frontend && npm run type-check` passes for the `admin-shared/` scope with zero errors.
- AC-4: `cd frontend && npm run test` — all existing tests remain green, including `frontend/tests/legacy/admin-dashboard.test.js`, `admin-performance.test.js`, `admin-user-usage-kpi.test.js`.
- AC-5: `cd frontend && npm run build` succeeds (no Vite resolution failures).
- AC-6: `cd frontend && npm run css:check` passes (no CSS governance regression).
- AC-7: A barrel `frontend/src/admin-shared/index.ts` is created or audited to export every public component/composable; partial barrels are not permitted.
- AC-8: All consumer imports in `admin-dashboard/`, `admin-performance/`, `admin-user-usage-kpi/` resolve correctly without `.js` extension specifiers.
- AC-9: No `as any` is introduced where a typed alternative exists; declared-interface + `@ts-expect-error` + cast pattern used for imports from not-yet-migrated directories.
- AC-10: No runtime behaviour change in affected admin pages (smoke-verified by existing legacy test suites).
- AC-11: Any Python parity tests and Vitest tests referencing renamed files by `.js` path are updated to `.ts` or extension-less specifiers.
- AC-12: `cdd-kit gate migrate-admin-shared-ts --strict` passes.

## Tasks Not Applicable
- not-applicable: 2.1, 2.3, 2.4, 2.5, 3.2, 3.3, 3.4, 3.5, 4.1, 4.3, 5.1, 5.2, 6.4

## Clarifications or Assumptions
- No index barrel currently exists for admin-shared/; one must be created as part of this migration (per Phase 1c learning).
- admin-dashboard/, admin-performance/, admin-user-usage-kpi/ are import-site consumers; they are read for verification only, not migrated.
- Node ≥22.6 already satisfied by environment.yml pin.

## Context Manifest Draft
See context-manifest.md (written separately per Step 2.3).
