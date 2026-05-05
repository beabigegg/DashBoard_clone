# Change Classification

## Change Types
- primary: refactor, type-system-migration
- secondary: ci-cd-change (type-check gate scope expansion)

## Risk Level
- medium

## Impact Radius
- module-level (frontend/src/core/ only; downstream feature apps import from this barrel but its public surface is preserved)

## Tier
- 2

## Architecture Review Required
- no
- reason: module-level rename, no architectural decision

## Required Artifacts
Always required: change-request.md, change-classification.md, test-plan.md, ci-gates.md, tasks.yml

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | rename-only migration; no behavior to characterize |
| proposal.md | no | scope and approach fully defined in change-request and external ts-migration-plan.md |
| spec.md | no | no new feature spec; types are derived from existing runtime shapes |
| design.md | no | no architectural decision; standard .js -> .ts rename + ApiResponse<T> generic |
| qa-report.md | no | qa-reviewer log entry sufficient at Tier 2 |
| regression-report.md | no | existing test suites (core/, schema-guard, unwrap-api-result, legacy/) cover regression; pass/fail captured in agent logs |

## Required Contracts
- API: none (informational only — contracts/api/api-contract.md unchanged; ApiResponse<T> generic mirrors the existing runtime envelope)
- CSS/UI: none
- Env: none
- Data shape: none (endpoint-schemas runtime objects retained; TS interfaces are a parallel static layer)
- Business logic: none
- CI/CD: type-check gate scope expansion (tsconfig.json `include` widens from `src/core/index.ts` to `src/core/**/*`); ci-gate-contract note already added in Phase 0

## Required Tests
- unit: rerun frontend/tests/core/api-dedup.test.js, frontend/tests/schema-guard.test.js, frontend/tests/unwrap-api-result.test.js, plus all frontend/tests/legacy/*.test.js after rename — must pass unchanged
- contract: none
- integration: none required pre-merge; existing Vitest suite is sufficient
- E2E: none
- visual: none
- data-boundary: none (schema-guard runtime validation preserved; covered by existing schema-guard.test.js)
- resilience: none
- fuzz/monkey: none
- stress: none
- soak: none

Additional gate: `npm run type-check` (vue-tsc --noEmit) must pass with 0 errors after tsconfig.json include is widened to `src/core/**/*`.

## Required Agents
1. contract-reviewer — confirm no contract drift before implementation
2. test-strategist — produce test-plan.md mapping AC → existing tests + type-check gate
3. frontend-engineer — execute the migration (renames, ApiResponse<T>, tsconfig widening)
4. ci-cd-gatekeeper — produce ci-gates.md (type-check expanded scope, existing Vitest jobs)
5. qa-reviewer — release readiness decision

## Inferred Acceptance Criteria
- AC-1: All 21 `.js` files in `frontend/src/core/` are renamed to `.ts`; no `.js` source files remain in `frontend/src/core/` after migration.
- AC-2: An `ApiResponse<T>` generic interface is defined (in `frontend/src/core/`) and is exported from the `frontend/src/core/index.ts` barrel.
- AC-3: `endpoint-schemas.js` runtime schema objects are converted to TS interfaces, and the runtime validation logic in `schema-guard.ts` is preserved unchanged in behavior (dual-layer: static interfaces + runtime guard).
- AC-4: `frontend/tsconfig.json` `include` is widened from `["src/core/index.ts"]` to `["src/core/**/*"]`, and `npm run type-check` passes with 0 errors.
- AC-5: All existing core/ test suites pass without modification to assertions: frontend/tests/core/api-dedup.test.js, frontend/tests/schema-guard.test.js, frontend/tests/unwrap-api-result.test.js, and all frontend/tests/legacy/*.test.js files.
- AC-6: Every `any` type is accompanied by a `// TODO: type <explanation>` comment; no bare `any` and no `@ts-ignore` without a paired `// TODO:` comment.
- AC-7: No runtime behavior change — `npm run build` succeeds and the bundled output is functionally equivalent (verified by passing test suite).
- AC-8: Public exports from `frontend/src/core/index.ts` preserve their existing names and signatures so downstream feature apps compile against them unchanged.

## Tasks Not Applicable
- not-applicable: 2.1, 2.2, 2.3, 2.4, 2.5, 3.2, 3.3, 3.4, 3.5, 4.1, 4.3, 5.1, 5.2

## Clarifications or Assumptions
- Test files (frontend/tests/**/*.test.js) remain in JavaScript; only frontend/src/core/ source files migrate to .ts.
- ApiResponse<T> will live in a new frontend/src/core/types.ts or co-located in unwrap-api-result.ts; exact filename is implementer decision.
- contracts/ci/ci-gate-contract.md already documents `npm run type-check` from Phase 0; ci-cd-gatekeeper should verify and only add a note if scope-widening requires one.
- No lockfile changes (typescript, vue-tsc already installed in Phase 0).
- If strict TS surfaces a real business-logic bug, implementer should stop and file a Context Expansion Request rather than silently fixing it under this rename-only scope.

## Context Manifest Draft

### Affected Surfaces
- frontend/src/core/ (21 .js files + existing index.ts placeholder)
- frontend/tsconfig.json (include scope expansion)
- frontend/tests/core/, frontend/tests/schema-guard.test.js, frontend/tests/unwrap-api-result.test.js, frontend/tests/legacy/* (test imports may need extension fixups; tests stay .js)
- ts-migration-plan.md (project-root reference, read-only)

### Allowed Paths
- specs/changes/migrate-core-to-typescript/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/core/
- frontend/tsconfig.json
- frontend/vite.config.ts
- frontend/package.json
- frontend/vitest.config.js
- frontend/tests/core/
- frontend/tests/schema-guard.test.js
- frontend/tests/unwrap-api-result.test.js
- frontend/tests/legacy/
- frontend/tests/pending-jobs-registry.test.js
- ts-migration-plan.md
- contracts/ci/ci-gate-contract.md
- contracts/api/api-contract.md
- .github/workflows/frontend-tests.yml
- .github/workflows/contract-driven-gates.yml

### Required Contracts
- none (read-only references only)

### Required Tests
- frontend/tests/core/api-dedup.test.js
- frontend/tests/schema-guard.test.js
- frontend/tests/unwrap-api-result.test.js
- frontend/tests/legacy/datetime.test.js
- frontend/tests/legacy/autocomplete.test.js
- frontend/tests/legacy/wip-derive.test.js
- frontend/tests/legacy/shell-navigation.test.js
- frontend/tests/pending-jobs-registry.test.js

### Agent Work Packets

#### change-classifier
- specs/changes/migrate-core-to-typescript/
- specs/context/project-map.md
- specs/context/contracts-index.md

#### contract-reviewer
- specs/changes/migrate-core-to-typescript/
- contracts/api/api-contract.md
- contracts/ci/ci-gate-contract.md
- frontend/src/core/
- frontend/tsconfig.json

#### test-strategist
- specs/changes/migrate-core-to-typescript/
- frontend/tests/core/
- frontend/tests/schema-guard.test.js
- frontend/tests/unwrap-api-result.test.js
- frontend/tests/legacy/
- frontend/tests/pending-jobs-registry.test.js
- frontend/package.json
- frontend/tsconfig.json

#### frontend-engineer
- specs/changes/migrate-core-to-typescript/
- frontend/src/core/
- frontend/tsconfig.json
- frontend/vite.config.ts
- frontend/package.json
- frontend/vitest.config.js
- frontend/tests/core/
- frontend/tests/schema-guard.test.js
- frontend/tests/unwrap-api-result.test.js
- frontend/tests/legacy/
- frontend/tests/pending-jobs-registry.test.js
- ts-migration-plan.md

#### ci-cd-gatekeeper
- specs/changes/migrate-core-to-typescript/
- .github/workflows/frontend-tests.yml
- .github/workflows/contract-driven-gates.yml
- frontend/package.json
- frontend/tsconfig.json
- contracts/ci/ci-gate-contract.md

#### qa-reviewer
- specs/changes/migrate-core-to-typescript/
- frontend/src/core/
- frontend/tsconfig.json
- frontend/package.json
- .github/workflows/frontend-tests.yml
- .github/workflows/contract-driven-gates.yml

### Context Expansion Requests
- (none at classification time)
