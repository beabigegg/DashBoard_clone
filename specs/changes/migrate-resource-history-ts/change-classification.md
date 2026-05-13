# Change Classification

## Change Types
- primary: TypeScript migration (rename .js → .ts, add `<script setup lang="ts">` to SFCs)
- secondary: audit and remove stale .js import specifiers, expand tsconfig.json include to cover src/resource-history/**/*

## Risk Level
- low

## Impact Radius
- isolated (resource-history/ source files only; shared layers — core/, shared-composables/, shared-ui/, resource-shared/ — are read-only reference targets; no runtime behavior change)

## Tier
- 4

## Architecture Review Required
- no
- reason: follows established Phase 3 migration pattern (same as resource-status, qc-gate, hold-history, reject-history, wip migrations)

## Required Artifacts
Always required: change-request.md, change-classification.md, test-plan.md, ci-gates.md, tasks.yml

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | pure rename; no behavior change |
| proposal.md | no | scope is fully specified in change-request.md |
| spec.md | no | no new feature or API surface |
| design.md | no | no architecture or UX change |
| qa-report.md | no | no branching audit decision; all ACs are mechanical and verifiable by CI |
| regression-report.md | no | no behavior change; Vitest + type-check suffice |

## Required Contracts
- API: none
- CSS/UI: contracts/css/css-contract.md — confirm style.css is not modified; no new class violations introduced
- Env: none
- Data shape: none
- Business logic: none
- CI/CD: contracts/ci/ci-gate-contract.md — schema-version bump 1.3.8 → 1.3.9 (patch) + Gate Compatibility Note documenting Phase 3 item #15 scope expansion; contracts/CHANGELOG.md entry [ci 1.3.9]

## Required Tests
- unit: existing Vitest suite must pass with zero regressions after migration
- contract: `npm run css:check` must exit 0; `npm run type-check` must exit 0 with src/resource-history/**/* now included in tsconfig.json
- integration: none new — no route or API change
- E2E: none new — no behavioral change
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
- AC-1: `main.js` → `main.ts` with typed `createApp` call; `index.html` left unchanged (Vite resolves `main.ts` automatically — per CLAUDE.md TypeScript Migration Rules)
- AC-2: `useResourceHistoryDuckDB.js` → `useResourceHistoryDuckDB.ts` with explicit TypeScript types for all public return values (reactive refs, computed properties, and composable return interface); `DuckDBClient.sendQuery` result rows typed as `unknown[]`; `ResourceFilterSnapshot`, `ResourceHistoryQueryParams`, and `ResourceKpi` types imported from `../../core/` with extension-free specifiers; no bare `any` without `// TODO: type <reason>`
- AC-3: `App.vue` uses `<script setup lang="ts">` with typed reactive state and typed composable consumption; all stale `.js` import specifiers replaced with extension-free specifiers
- AC-4: `components/FilterBar.vue` uses `<script setup lang="ts">` with typed `defineProps` and `defineEmits`
- AC-5: `components/KpiCards.vue` uses `<script setup lang="ts">` with typed `defineProps`; `ResourceKpi` type used where applicable
- AC-6: `components/TrendChart.vue`, `components/StackedChart.vue`, `components/ComparisonChart.vue`, and `components/HeatmapChart.vue` each use `<script setup lang="ts">` with typed `defineProps`; echarts callback parameters annotated with `// TODO: type echarts callback` (per CLAUDE.md TypeScript Migration Rules — known library gap)
- AC-7: `components/DetailSection.vue` uses `<script setup lang="ts">` with typed `defineProps` and `defineEmits`; column descriptor `value` callback `node` parameters annotated with `// TODO: type hierarchy node union` (per CLAUDE.md TypeScript Migration Rules); `ResourceKpi`-derived metrics accessed via typed interface where feasible
- AC-8: No stale `.js` specifiers remain in any migrated file; all internal imports use extension-free specifiers (per CLAUDE.md TypeScript Migration Rules)
- AC-9: `tsconfig.json` include array expanded to cover `"src/resource-history/**/*"` as item #15
- AC-10: `contracts/ci/ci-gate-contract.md` schema-version bumped to 1.3.9; `contracts/CHANGELOG.md` entry [ci 1.3.9] added documenting Phase 3 item #15 scope expansion
- AC-11: `npm run type-check` exits 0; `npm run build` exits 0; `npm run css:check` exits 0; `npm run test` exits 0
- AC-12: Legacy test `frontend/tests/legacy/resource-history.test.js` passes unchanged (inline replicas — no import from source; no regex updates needed)

## Tasks Not Applicable
- not-applicable: 2.1, 2.3, 2.4, 2.5, 3.2, 3.3, 3.4, 3.5, 4.1, 4.3, 5.1, 5.2, 6.4

## Clarifications or Assumptions
- `index.html` references `./main.js` — do NOT update; Vite resolves `main.ts` correctly at build time. This is a cosmetic pre-existing pattern across all feature apps (per CLAUDE.md TypeScript Migration Rules).
- `style.css` is excluded from migration scope (no TypeScript content).
- `components/TrendChart.vue`, `StackedChart.vue`, `ComparisonChart.vue`, and `HeatmapChart.vue` contain echarts formatter/tooltip callback parameters that lack precise library types; annotate with `// TODO: type echarts callback` rather than blocking migration (per CLAUDE.md TypeScript Migration Rules).
- `components/DetailSection.vue` defines its own local hierarchy node shape (workcenter/family/resource levels) distinct from the `ResourceNode/FamilyNode/GroupNode` union in resource-status/MatrixSection.vue. Column descriptor `value(node)` callbacks must use `// TODO: type hierarchy node union` annotation per CLAUDE.md TypeScript Migration Rules until the node union is stabilized in resource-shared.
- `useResourceHistoryDuckDB.js` imports `getDuckDBClient` and `fetchParquetBuffer` from `../../core/duckdb-client.js` — drop `.js` extension only (not `.ts`); import resolution is automatic.
- `ResourceFilterSnapshot`, `ResourceHistoryQueryParams`, and `ResourceKpi` are already exported from `frontend/src/core/index.ts` — import from `../../core/` (extension-free).
- No Python parity tests (`tests/test_frontend_*_parity.py`) reference resource-history files by path; no Python test changes are required.
- The legacy test `frontend/tests/legacy/resource-history.test.js` uses fully inline formula replicas with no imports from source — no regex updates needed (per change-request.md).
- The resource-history backend routes and service are unaffected — this change is purely frontend.
- No shared barrel (`index.ts`) exists in resource-history/ — this is a standalone feature app with no barrel file to audit.
- `tsconfig.json` currently includes 14 entries; `src/resource-history/**/*` is added as item #15 (after `src/qc-gate/**/*`).

## Context Manifest Draft

### Affected Surfaces
- `frontend/src/resource-history/` (migration target — 10 files: main.js, useResourceHistoryDuckDB.js, App.vue, components/FilterBar.vue, components/KpiCards.vue, components/TrendChart.vue, components/StackedChart.vue, components/ComparisonChart.vue, components/HeatmapChart.vue, components/DetailSection.vue)
- `frontend/tsconfig.json` (include array expansion — item #15)
- `contracts/ci/ci-gate-contract.md` (schema-version bump 1.3.8 → 1.3.9 + Gate Compatibility Note)
- `contracts/CHANGELOG.md` (new entry [ci 1.3.9])

### Allowed Paths
- specs/changes/migrate-resource-history-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/resource-history/
- frontend/src/core/
- frontend/src/shared-composables/
- frontend/src/shared-ui/
- frontend/src/resource-shared/
- frontend/tests/legacy/resource-history.test.js
- frontend/tsconfig.json
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md

### Required Contracts
- contracts/ci/ci-gate-contract.md
- contracts/css/css-contract.md

### Required Tests
- frontend/tests/legacy/resource-history.test.js (read-only guard — no changes needed)
- `npm run type-check` (zero errors with src/resource-history/**/* in tsconfig)
- `npm run test` (full Vitest suite — zero regressions)
- `npm run css:check` (zero violations)
- `npm run build` (clean build)

### Agent Work Packets

#### change-classifier
- specs/changes/migrate-resource-history-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md

#### contract-reviewer
- specs/changes/migrate-resource-history-ts/
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md
- frontend/tsconfig.json

#### test-strategist
- specs/changes/migrate-resource-history-ts/
- frontend/src/resource-history/
- frontend/tests/legacy/resource-history.test.js

#### frontend-engineer
- specs/changes/migrate-resource-history-ts/
- frontend/src/resource-history/
- frontend/src/core/
- frontend/src/shared-composables/
- frontend/src/shared-ui/
- frontend/src/resource-shared/
- frontend/tsconfig.json

#### ci-cd-gatekeeper
- specs/changes/migrate-resource-history-ts/
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md
- frontend/tsconfig.json

#### qa-reviewer
- specs/changes/migrate-resource-history-ts/
- frontend/src/resource-history/
