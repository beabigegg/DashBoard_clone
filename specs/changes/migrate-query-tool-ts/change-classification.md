# Change Classification

## Change Types
- primary: TypeScript migration (JS → TS rename + type annotations)
- secondary: CI gate verification (type-check, vitest, pytest path audit)

## Risk Level
- low

## Impact Radius
- isolated (frontend/src/query-tool/ only)

## Tier
- 2

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
| qa-report.md | yes | verify type-check + test suite results |
| regression-report.md | no | |

## Required Contracts
- API: none — no API surface changes
- CSS/UI: none
- Env: none
- Data shape: none
- Business logic: none
- CI/CD: type-check gate must exit 0 post-migration

## Required Tests
- unit: existing Vitest tests must stay green (npm run test)
- contract: none
- integration: none
- E2E: informational only (nightly) — query-tool.spec.js, query-tool-url-state.spec.js
- visual: none
- data-boundary: none
- resilience: none
- fuzz/monkey: none
- stress: none
- soak: none

## Required Agents
1. frontend-engineer — rename JS→TS, add types, convert SFC script blocks, audit Python test paths
2. qa-reviewer — verify type-check + Vitest + pytest pass, no runtime regressions

## Inferred Acceptance Criteria
- AC-1: All 9 JS files renamed to .ts with valid TypeScript annotations
- AC-2: `npm run type-check` exits 0 (no TypeScript errors)
- AC-3: All existing frontend unit tests pass (`npm run test`)
- AC-4: All Python tests that reference query-tool files pass (`pytest`)
- AC-5: Vue SFCs use `<script lang="ts">` where applicable
- AC-6: No runtime regressions in query-tool feature (page loads, queries execute)

## Tasks Not Applicable
- not-applicable: 2.1, 2.2, 2.3, 2.4, 2.5, 3.2, 3.4, 3.5, 4.1, 4.3, 5.1, 5.2

## Clarifications or Assumptions
- `index.html` references `./main.js` — intentionally NOT updated (Vite resolves main.ts at build time; this is project-wide convention)
- Static `vi.mock('...file.js')` calls do NOT need `.js` → `.ts` update (Vite handles transparently)
- Dynamic `import('...file.js')` specifiers must drop extension after rename
- SFC `<script>` blocks without `lang="ts"` attribute must be converted

## Context Manifest Draft

### Affected Surfaces
- frontend/src/query-tool/ (all .js files, all .vue SFCs)
- frontend/tests/legacy/query-tool-composables.test.js
- frontend/tests/query-tool/
- frontend/tests/abort/query-tool-abort.test.js
- frontend/tests/playwright/query-tool.spec.js
- frontend/tests/playwright/query-tool-url-state.spec.js
- tests/ (Python — audit for hardcoded .js paths referencing query-tool)

### Allowed Paths
- specs/changes/migrate-query-tool-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/query-tool/
- frontend/tests/legacy/
- frontend/tests/query-tool/
- frontend/tests/abort/
- frontend/tests/playwright/
- frontend/tsconfig.json
- frontend/vite.config.ts
- frontend/vitest.config.js
- frontend/package.json
- tests/

### Agent Work Packets
#### frontend-engineer
- specs/changes/migrate-query-tool-ts/
- frontend/src/query-tool/
- frontend/tests/legacy/
- frontend/tests/query-tool/
- frontend/tests/abort/
- frontend/tsconfig.json
- frontend/vite.config.ts
- frontend/vitest.config.js
- frontend/package.json
- tests/

#### qa-reviewer
- specs/changes/migrate-query-tool-ts/
- frontend/src/query-tool/
- frontend/tests/legacy/
- frontend/tests/query-tool/
- frontend/tests/abort/
- frontend/tests/playwright/
