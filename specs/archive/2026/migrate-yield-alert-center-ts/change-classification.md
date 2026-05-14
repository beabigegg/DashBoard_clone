# Change Classification

## Change Types
- primary: typescript-migration
- secondary: refactor

## Risk Level
- low

## Impact Radius
- module-level

## Tier
- 1

## Architecture Review Required
- no

## Required Artifacts
Always required: change-request.md, change-classification.md, test-plan.md, ci-gates.md, tasks.yml

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | |
| proposal.md | no | |
| spec.md | no | |
| design.md | no | |
| qa-report.md | yes | lightweight — record test pass/fail counts and TODO: type annotation sites |
| regression-report.md | no | |

## Required Contracts
- API: none
- CSS/UI: none
- Env: none
- Data shape: none
- Business logic: none
- CI/CD: none (pure rename, no workflow changes expected)

## Required Tests
- unit: frontend/tests/legacy/yield-alert-center-utils.test.js (utils.ts), frontend/tests/abort/yield-alert-abort.test.js (useYieldAlertDuckDB.ts)
- contract: frontend/tests/legacy/yield-alert-center-shell-contract.test.js
- integration: frontend/tests/yield-alert/App.cross-filter.test.js
- E2E: none (existing backend e2e unaffected)
- visual: none
- data-boundary: none
- resilience: none
- fuzz/monkey: none
- stress: none
- soak: none

## Required Agents
1. contract-reviewer
2. test-strategist
3. frontend-engineer
4. ci-cd-gatekeeper
5. qa-reviewer

## Inferred Acceptance Criteria
- AC-1: `npm run type-check` (vue-tsc --noEmit) passes with zero new errors after renaming main.js → main.ts, utils.js → utils.ts, useYieldAlertDuckDB.js → useYieldAlertDuckDB.ts and adding lang="ts" to all 5 SFCs.
- AC-2: All three affected test files (frontend/tests/legacy/yield-alert-center-utils.test.js, frontend/tests/abort/yield-alert-abort.test.js, frontend/tests/yield-alert/App.cross-filter.test.js) pass without logic changes (only import-specifier updates if needed).
- AC-3: frontend/tests/legacy/yield-alert-center-shell-contract.test.js and frontend/tests/validation/useYieldAlert.validation.test.js continue to pass unmodified.
- AC-4: tests/test_frontend_duckdb_parity.py passes — no hardcoded .js path references to useYieldAlertDuckDB.js remain unupdated.
- AC-5: npm run css:check passes (no new CSS violations).
- AC-6: No runtime behavior change — yield-alert-center renders and cross-filters identically, confirmed by App.cross-filter.test.js suite.

## Tasks Not Applicable
- not-applicable: 4.1, 4.3, 4.4, 3.3, 3.4, 3.5, 5.1, 5.2, 6.1

## Clarifications or Assumptions
- echarts callback parameters annotated with `// TODO: type echarts callback` per CLAUDE.md migration rules
- index.html entry point `./main.js` not updated per CLAUDE.md rule (Vite resolves main.ts automatically)
- No Python parity tests reference yield-alert JS files by path, but test_frontend_duckdb_parity.py must be audited

## Context Manifest Draft
### Affected Surfaces
- frontend/src/yield-alert-center/ (all files)
- frontend/tests/yield-alert/App.cross-filter.test.js
- frontend/tests/legacy/yield-alert-center-utils.test.js
- frontend/tests/abort/yield-alert-abort.test.js

### Allowed Paths
- specs/changes/migrate-yield-alert-center-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/yield-alert-center/
- frontend/tests/yield-alert/
- frontend/tests/legacy/yield-alert-center-utils.test.js
- frontend/tests/legacy/yield-alert-center-shell-contract.test.js
- frontend/tests/abort/yield-alert-abort.test.js
- frontend/tests/validation/useYieldAlert.validation.test.js
- frontend/src/core/shell-navigation.ts
- frontend/src/shared-composables/
- frontend/src/shared-ui/
- frontend/src/wip-shared/
- frontend/src/resource-shared/
- contracts/
- tests/test_frontend_duckdb_parity.py
- .github/workflows/
- frontend/tsconfig.json
- frontend/vitest.config.js
