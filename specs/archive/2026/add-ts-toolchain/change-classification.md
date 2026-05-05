# Change Classification

## Change Types
- primary: ci-cd-change, tooling-setup
- secondary: build-config-change

## Risk Level
- low

## Impact Radius
- module-level (frontend build/CI tooling only; no runtime/business code)

## Tier
- 3

## Architecture Review Required
- no
- reason: standard TS toolchain wiring; no architectural change

## Required Artifacts
Always required: change-request.md, change-classification.md, test-plan.md, ci-gates.md, tasks.yml

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | No existing behavior changed; greenfield tooling addition |
| proposal.md | no | Approach is mechanical and prescribed by change request |
| spec.md | no | No new business spec; tooling configuration only |
| design.md | no | No architectural design needed; standard TS toolchain wiring |
| qa-report.md | no | qa-reviewer inline review sufficient for Tier 3 tooling change |
| regression-report.md | no | No existing behavior modified; CI gate provides regression coverage |

## Required Contracts
- API: none
- CSS/UI: none
- Env: none
- Data shape: none
- Business logic: none
- CI/CD: `contracts/ci/ci-gate-contract.md` — add `frontend/type-check` gate entry

## Required Tests
- unit: none (no source code added)
- contract: `cdd-kit validate` must pass after adding the new CI gate entry
- integration: none
- E2E: none
- visual: none
- data-boundary: none
- resilience: none
- fuzz/monkey: none
- stress: none
- soak: none

Smoke verification (not formal test categories):
- `npm run type-check` exits 0
- `npm run dev`, `npm run build`, `npm run test` still succeed

## Required Agents
- contract-reviewer (verify CI gate contract entry; confirm other contracts unaffected)
- test-strategist (write test-plan.md)
- frontend-engineer (package.json deps + scripts; vite.config.js → vite.config.ts; tsconfig.json)
- dependency-security-reviewer (package.json / package-lock.json changes)
- ci-cd-gatekeeper (wire type-check step in .github/workflows/frontend-tests.yml; write ci-gates.md)
- qa-reviewer (release readiness; confirm dev/build/test unbroken)

## Inferred Acceptance Criteria
- AC-1: `frontend/package.json` declares `typescript`, `vue-tsc`, and `@types/node` as devDependencies compatible with existing Vite + Vue 3 setup.
- AC-2: `frontend/tsconfig.json` exists with `"strict": true`, `"allowJs": false`, and `include` scoped to `src/core/`; excludes rest of `src/`.
- AC-3: `frontend/vite.config.js` is renamed to `frontend/vite.config.ts` with no functional change to resolved Vite config (same plugins, aliases, server options).
- AC-4: `frontend/package.json` exposes a `type-check` script equivalent to `vue-tsc --noEmit`, and `npm run type-check` exits 0 on a clean checkout.
- AC-5: `.github/workflows/frontend-tests.yml` runs `npm run type-check` as a required step; a synthetic TS error in `src/core/` would cause CI to fail.
- AC-6: `npm run dev`, `npm run build`, and `npm run test` all continue to succeed unchanged (no regression).
- AC-7: `contracts/ci/ci-gate-contract.md` is updated to register the new `frontend/type-check` gate (name, command, blocking status, owning workflow).
- AC-8: `cdd-kit validate` passes after the contract update.

## Tasks Not Applicable
- not-applicable: 2.1, 2.2, 2.3, 2.4, 2.5, 3.2, 3.3, 3.4, 3.5, 4.1, 4.3, 5.1, 5.2

## Clarifications or Assumptions
- Existing CI workflow at `.github/workflows/frontend-tests.yml` has a Node setup + `npm ci` step that can be reused; no new workflow file needed.
- `package-lock.json` is checked in (standard for this repo) and will be updated as part of dep install.
- `vue-tsc` version must be compatible with installed Vue 3 minor version to avoid template-checker drift.
- Phase 0 does NOT add types to JS files; `allowJs: false` enforces this. Any future expansion of `tsconfig.include` is a separate change.

## Context Manifest Draft

### Affected Surfaces
- frontend build toolchain (Vite + TS compiler)
- CI workflow (frontend-tests)
- CI gate contract registry

### Allowed Paths
- specs/changes/add-ts-toolchain/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/package.json
- frontend/package-lock.json
- frontend/vite.config.js
- frontend/vite.config.ts
- frontend/tsconfig.json
- frontend/src/core/
- .github/workflows/frontend-tests.yml
- contracts/ci/ci-gate-contract.md

### Agent Work Packets

#### change-classifier
- specs/changes/add-ts-toolchain/
- specs/context/project-map.md
- specs/context/contracts-index.md

#### test-strategist
- specs/changes/add-ts-toolchain/
- frontend/package.json
- frontend/tsconfig.json
- .github/workflows/frontend-tests.yml
- contracts/ci/ci-gate-contract.md

#### frontend-engineer
- specs/changes/add-ts-toolchain/
- frontend/package.json
- frontend/package-lock.json
- frontend/vite.config.js
- frontend/vite.config.ts
- frontend/tsconfig.json
- frontend/src/core/
- contracts/ci/ci-gate-contract.md

#### dependency-security-reviewer
- specs/changes/add-ts-toolchain/
- frontend/package.json
- frontend/package-lock.json

#### contract-reviewer
- specs/changes/add-ts-toolchain/
- contracts/ci/ci-gate-contract.md
- frontend/package.json
- frontend/tsconfig.json

#### ci-cd-gatekeeper
- specs/changes/add-ts-toolchain/
- .github/workflows/frontend-tests.yml
- frontend/package.json
- contracts/ci/ci-gate-contract.md

#### qa-reviewer
- specs/changes/add-ts-toolchain/
- frontend/package.json
- frontend/tsconfig.json
- frontend/vite.config.ts
- .github/workflows/frontend-tests.yml
- contracts/ci/ci-gate-contract.md
