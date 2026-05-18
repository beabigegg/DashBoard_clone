# Change Classification

## Change Types
- primary: refactor (typescript-migration)
- secondary: ci-cd-change (ci-gate-contract scope expansion)

## Risk Level
- low

## Impact Radius
- module-level (single feature app: `frontend/src/mid-section-defect/`)

## Tier
- 3

## Architecture Review Required
- no
- reason: Pure type-system migration with no design decisions, no module-boundary changes, no data-flow changes.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)

| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | No behavior change. |
| proposal.md | no | Scope fully captured by change-request.md. |
| spec.md | no | No user-facing behavior decision. |
| design.md | no | No architecture review required. |
| qa-report.md | no | Routine type-check evidence fits in agent-log/*.yml. |
| regression-report.md | no | No behavior change; existing suite is the regression check. |
| visual-review-report.md | no | No UI output change. |
| monkey-test-report.md | no | Out of scope for type-migration. |
| stress-soak-report.md | no | Out of scope for type-migration. |

Artifact minimization:
- Prefer optional `agent-log/*.yml` pointers for routine review evidence.
- Create report markdown only for blocking findings, approved-with-risk, excluded pre-existing failures, visual evidence bundles, or high-risk load/soak results.
- Later artifacts should reference earlier artifacts by path/section/id instead of duplicating full content.

## Required Contracts
- API: none
- CSS/UI: none
- Env: none
- Data shape: none
- Business logic: none
- CI/CD: `contracts/ci/ci-gate-contract.md` — patch version bump with `### frontend-type-check scope expansion` note documenting before/after `tsconfig.json include` state; matching entry in `contracts/CHANGELOG.md`.

## Required Tests
- unit: existing Vitest tests (`frontend/tests/legacy/mid-section-defect-composables.test.js`, `frontend/tests/legacy/msd-completeness-warning.test.js`) must pass after rename; audit and repair as needed.
- contract: none
- integration: none new; existing Python tests must pass after `.js → .ts` path audit.
- E2E: `tests/e2e/test_mid_section_defect_e2e.py` must continue to pass.
- visual: none
- data-boundary: none
- resilience: none
- fuzz/monkey: none
- stress: `tests/stress/test_mid_section_defect_stress.py` must not be broken (not pre-merge gate).
- soak: none

## Required Agents
1. contract-reviewer
2. test-strategist
3. ci-cd-gatekeeper
4. implementation-planner
5. frontend-engineer
6. qa-reviewer

## Inferred Acceptance Criteria
- AC-1: All `.js` files under `frontend/src/mid-section-defect/` are renamed to `.ts` with TypeScript annotations; `index.html` Vite entry (`./main.js`) is NOT modified.
- AC-2: `frontend/tsconfig.json` `include` is expanded to cover `mid-section-defect`; `npm run type-check` passes with zero errors.
- AC-3: `npm run test` passes; any Vitest file using `require()` against a renamed module is converted to static `import`; `vi.mock('...file.js')` static specifiers are left unchanged.
- AC-4: `pytest` passes; all hardcoded `.js` paths referencing `mid-section-defect` in `tests/**/*.py` are audited and updated to `.ts` where required.
- AC-5: `contracts/ci/ci-gate-contract.md` is bumped to next patch version with `### frontend-type-check scope expansion` note (before/after `tsconfig.json include` state); `contracts/CHANGELOG.md` has matching entry.
- AC-6: No breaking prop/emit changes introduced to `frontend/src/shared-ui/components/MultiSelect.vue`; any additions must be additive.
- AC-7: Dynamic `import('...file.js')` specifiers targeting renamed files have `.js` extension dropped; SFC `.js` import specifiers inside migrated files have extension dropped (not renamed to `.ts`).
- AC-8: `frontend/src/mid-section-defect/index.html` Vite entry (`./main.js`) is NOT modified.

## Tasks Not Applicable
- not-applicable: 1.3, 2.1, 2.2, 2.3, 2.4, 2.5, 3.2, 3.3, 3.4, 3.5, 4.1, 4.3, 5.1, 5.2, 6.4

## Clarifications or Assumptions
- Assumption: No Python parity test currently invokes `node --experimental-strip-types` against mid-section-defect source; `environment.yml` already pins `nodejs>=22.6` so no env change is needed if one is found.
- Assumption: `mid-section-defect` has no SFC-paired `.test.ts`; if any is added during migration, `frontend/vitest.config.js` `include` must already list `src/**/*.test.ts` (verified from prior `fix-prod-history-multiselect-filter` migration).
- Assumption: Tier 1 pre-merge gates are `npm run type-check`, `npm run test`, `pytest`, `npm run css:check`, `cdd-kit validate`. Tasks 6.2/6.3 may be marked `done` before CI confirmation when all local commands pass. Task 6.4 marked `skipped` (no nightly/weekly/manual gates defined).

## Context Manifest Draft

### Affected Surfaces
- `frontend/src/mid-section-defect/` (feature app — all JS files to be renamed)
- `frontend/tsconfig.json` (include scope expansion)
- `contracts/ci/ci-gate-contract.md` + `contracts/CHANGELOG.md` (procedural patch bump)
- `frontend/tests/legacy/mid-section-defect-composables.test.js`, `frontend/tests/legacy/msd-completeness-warning.test.js` (audit/repair if needed)
- `tests/e2e/test_mid_section_defect_e2e.py` (audit for `.js` path references)

### Allowed Paths
- specs/changes/migrate-mid-section-defect-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/mid-section-defect/
- frontend/src/shared-ui/components/
- frontend/src/shared-composables/
- frontend/src/core/
- frontend/tsconfig.json
- frontend/vitest.config.js
- frontend/package.json
- frontend/tests/legacy/
- tests/e2e/test_mid_section_defect_e2e.py
- tests/stress/test_mid_section_defect_stress.py
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md
- CLAUDE.md

### Agent Work Packets

#### change-classifier
- specs/changes/migrate-mid-section-defect-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md

#### contract-reviewer
- specs/changes/migrate-mid-section-defect-ts/
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md

#### test-strategist
- specs/changes/migrate-mid-section-defect-ts/
- frontend/tests/legacy/
- tests/e2e/test_mid_section_defect_e2e.py

#### ci-cd-gatekeeper
- specs/changes/migrate-mid-section-defect-ts/
- contracts/ci/ci-gate-contract.md

#### implementation-planner
- specs/changes/migrate-mid-section-defect-ts/
- frontend/src/mid-section-defect/
- frontend/tsconfig.json
- CLAUDE.md

#### frontend-engineer
- specs/changes/migrate-mid-section-defect-ts/
- frontend/src/mid-section-defect/
- frontend/src/shared-ui/components/
- frontend/src/shared-composables/
- frontend/src/core/
- frontend/tsconfig.json
- frontend/vitest.config.js
- frontend/package.json
- frontend/tests/legacy/
- tests/e2e/test_mid_section_defect_e2e.py
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md

#### qa-reviewer
- specs/changes/migrate-mid-section-defect-ts/
- frontend/src/mid-section-defect/
- frontend/tsconfig.json
- contracts/ci/ci-gate-contract.md
