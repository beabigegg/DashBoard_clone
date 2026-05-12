# Change Classification

## Change Types
- primary: TypeScript migration (rename .js → .ts, add lang="ts" to SFCs)
- secondary: remove @ts-expect-error cross-phase suppressions, create index.ts barrel, fix all stale .js specifiers, expand tsconfig.json include

## Risk Level
- low

## Impact Radius
- module-level (wip-shared/ source files + compile-time consumer fixes in shared-composables/, shared-ui/, hold-detail/)

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
| qa-report.md | yes | release readiness evidence; @ts-expect-error cleanup scope warrants explicit per-AC record |
| regression-report.md | no | |

## Required Contracts
- API: none
- CSS/UI: css-contract.md — confirm no new violations (styles.css, pareto-styles.css not modified)
- Env: none
- Data shape: none
- Business logic: none
- CI/CD: ci-gate-contract.md — schema-version bump to 1.3.4 + Gate Compatibility Note; contracts/CHANGELOG.md entry

## Required Tests
- unit: frontend/tests/legacy/resource-status.test.js is unaffected; no new wip-shared test files needed
- (all others): none new — existing Vitest suite passes; loading-standardization.test.js verifies styles.css

## Required Agents
- contract-reviewer
- test-strategist
- frontend-engineer
- ci-cd-gatekeeper
- qa-reviewer

## Inferred Acceptance Criteria
- AC-1: constants.js → constants.ts with no implicit any; NON_QUALITY_HOLD_REASONS typed as readonly string[], NON_QUALITY_HOLD_REASON_SET as ReadonlySet<string>
- AC-2: composables/useAutocomplete.js → useAutocomplete.ts; typed options parameter, internal .js imports dropped
- AC-3: composables/useAutoRefresh.js → useAutoRefresh.ts; typed options parameter
- AC-4: HoldLotTable.vue uses `<script setup lang="ts">` with typed defineProps; internal useSortableTable.js import dropped
- AC-5: Pagination.vue uses `<script setup lang="ts">` with typed defineProps
- AC-6: ParetoSection.vue uses `<script setup lang="ts">` with typed defineProps; internal wip-derive.js import dropped
- AC-7: index.ts barrel created — exports 3 components + 2 composables + 2 constants exports (complete)
- AC-8: @ts-expect-error removed from shared-composables/useAutocomplete.ts, useAutoRefresh.ts, shared-ui/components/PaginationControl.vue
- AC-9: All stale .js specifiers in consumers fixed (hold-detail/App.vue, useAutocomplete.ts, useAutoRefresh.ts, PaginationControl.vue)
- AC-10: tsconfig.json include expanded to cover src/wip-shared/**/*
- AC-11: ci-gate-contract.md schema-version 1.3.4; contracts/CHANGELOG.md [ci 1.3.4] entry added
- AC-12: npm run type-check exits 0; npm run build exits 0; css:check exits 0
- AC-13: All existing legacy tests pass (no regressions from specifier fixes or @ts-expect-error removal)
- AC-14: No as any; no new @ts-expect-error introduced
- AC-15: cdd-kit gate --strict passes

## Tasks Not Applicable
- not-applicable: 2.1, 2.3, 2.4, 2.5, 3.2, 3.3, 3.4, 3.5, 4.1, 4.3, 5.1, 5.2, 6.4

## Clarifications or Assumptions
- @ts-expect-error lines in shared-composables/ and PaginationControl.vue were explicitly placed as placeholders for this phase; removing them is the required and expected action
- styles.css and pareto-styles.css are intentionally excluded from migration scope
- No Python parity tests reference wip-shared

## Context Manifest Draft

### Affected Surfaces
- frontend/src/wip-shared/ (migration target)
- frontend/src/shared-composables/ (@ts-expect-error cleanup + specifier fixes)
- frontend/src/shared-ui/components/PaginationControl.vue (@ts-expect-error cleanup)
- frontend/src/hold-detail/App.vue (stale .js specifier fix)
- frontend/tsconfig.json (include array expansion)
- contracts/ci/ci-gate-contract.md (schema-version bump + Gate Compatibility Note)
- contracts/CHANGELOG.md (new entry [ci 1.3.4])

### Allowed Paths
- specs/changes/migrate-wip-shared-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/wip-shared/
- frontend/src/shared-composables/
- frontend/src/shared-ui/components/PaginationControl.vue
- frontend/src/hold-detail/App.vue
- frontend/tsconfig.json
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md
- specs/archive/2026/migrate-admin-shared-ts/

### Agent Work Packets

#### contract-reviewer
- specs/changes/migrate-wip-shared-ts/
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md
- frontend/tsconfig.json

#### test-strategist
- specs/changes/migrate-wip-shared-ts/
- frontend/src/wip-shared/

#### frontend-engineer
- specs/changes/migrate-wip-shared-ts/
- frontend/src/wip-shared/
- frontend/src/shared-composables/
- frontend/src/shared-ui/components/PaginationControl.vue
- frontend/src/hold-detail/App.vue
- frontend/tsconfig.json

#### ci-cd-gatekeeper
- specs/changes/migrate-wip-shared-ts/
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md
- frontend/tsconfig.json

#### qa-reviewer
- specs/changes/migrate-wip-shared-ts/
