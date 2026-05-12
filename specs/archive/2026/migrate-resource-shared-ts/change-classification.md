# Change Classification

## Change Types
- primary: TypeScript migration (rename .js → .ts, add lang="ts" to SFCs)
- secondary: create index.ts barrel, fix stale .js import specifiers, expand tsconfig.json include

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

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | |
| proposal.md | no | |
| spec.md | no | |
| design.md | no | |
| qa-report.md | yes | release readiness evidence for Phase 2 migration |
| regression-report.md | no | |

## Required Contracts
- API: none
- CSS/UI: css-contract.md — confirm no new violations (styles.css not modified)
- Env: none
- Data shape: none
- Business logic: none
- CI/CD: ci-gate-contract.md — schema-version bump to 1.3.3 + Gate Compatibility Note; contracts/CHANGELOG.md entry

## Required Tests
- unit: frontend/tests/legacy/resource-status.test.js (existing; must pass without modification)
- contract: none new
- integration: none
- E2E: playwright gates (pre-existing; no new tests needed)
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
- AC-1: constants.js renamed to constants.ts with no implicit any; all 7 exports + 3 functions typed
- AC-2: HierarchyTable.vue uses `<script setup lang="ts">` with typed defineProps (generic syntax)
- AC-3: MultiSelect.vue uses `<script setup lang="ts">` with typed defineProps (generic syntax)
- AC-4: index.ts barrel created — exports 2 components + all constants named exports (complete, no partial barrel)
- AC-5: All 5 stale .js specifiers in consumers dropped to extension-free (KpiCards.vue, StackedChart.vue, App.vue, EquipmentCard.vue, MatrixSection.vue)
- AC-6: frontend/tsconfig.json include array expanded to cover src/resource-shared/**/*
- AC-7: ci-gate-contract.md schema-version bumped to 1.3.3; contracts/CHANGELOG.md [ci 1.3.3] entry added
- AC-8: npm run type-check exits 0 across all migrated modules
- AC-9: npm run build exits 0
- AC-10: css:check exits 0 — 0 new violations
- AC-11: 35+ legacy tests pass (resource-status.test.js and pre-existing suites)
- AC-12: No as any; no @ts-expect-error needed (core/ already migrated Phase 1a)
- AC-13: cdd-kit gate --strict passes

## Tasks Not Applicable
- not-applicable: 2.1, 2.3, 2.4, 2.5, 3.2, 3.3, 3.4, 3.5, 4.1, 4.3, 5.1, 5.2, 6.4

## Clarifications or Assumptions
- ts-resolver-loader.mjs auto-remaps .js → .ts imports in legacy tests; resource-status.test.js requires no change
- styles.css is intentionally excluded from migration scope; no CSS contract changes needed

## Context Manifest Draft

### Affected Surfaces
- frontend/src/resource-shared/ (migration target: constants.js, HierarchyTable.vue, MultiSelect.vue, new index.ts)
- frontend/src/resource-history/components/ (consumer: stale .js specifier fixes in KpiCards.vue, StackedChart.vue)
- frontend/src/resource-status/ (consumer: stale .js specifier fixes in App.vue, EquipmentCard.vue, MatrixSection.vue)
- frontend/tsconfig.json (include array expansion)
- contracts/ci/ci-gate-contract.md (schema-version bump + Gate Compatibility Note)
- contracts/CHANGELOG.md (new entry [ci 1.3.3])

### Allowed Paths
- specs/changes/migrate-resource-shared-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/resource-shared/
- frontend/src/resource-history/components/
- frontend/src/resource-status/
- frontend/tsconfig.json
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md
- frontend/tests/legacy/resource-status.test.js
- specs/archive/2026/migrate-admin-shared-ts/

### Agent Work Packets

#### contract-reviewer
- specs/changes/migrate-resource-shared-ts/
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md
- frontend/tsconfig.json

#### test-strategist
- specs/changes/migrate-resource-shared-ts/
- frontend/src/resource-shared/
- frontend/tests/legacy/resource-status.test.js

#### frontend-engineer
- specs/changes/migrate-resource-shared-ts/
- frontend/src/resource-shared/
- frontend/src/resource-history/components/
- frontend/src/resource-status/
- frontend/tsconfig.json
- frontend/src/core/types.ts

#### ci-cd-gatekeeper
- specs/changes/migrate-resource-shared-ts/
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md
- frontend/tsconfig.json

#### qa-reviewer
- specs/changes/migrate-resource-shared-ts/
