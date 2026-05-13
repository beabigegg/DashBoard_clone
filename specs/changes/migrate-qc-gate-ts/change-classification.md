# Change Classification

## Change Types
- primary: TypeScript migration (rename .js → .ts, add `<script setup lang="ts">` to SFCs)
- secondary: audit and remove stale .js import specifiers, expand tsconfig.json include to cover src/qc-gate/**/*, annotate echarts click-handler callback with TODO comment

## Risk Level
- low

## Impact Radius
- isolated (qc-gate/ source files only; shared layers — core/, shared-composables/, shared-ui/ — are read-only reference targets; no runtime behavior change)

## Tier
- 3

## Architecture Review Required
- no

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
- CI/CD: contracts/ci/ci-gate-contract.md — schema-version bump 1.3.7 → 1.3.8 (patch) + Gate Compatibility Note documenting Phase 3 item #17 scope expansion; contracts/CHANGELOG.md entry [ci 1.3.8]

## Required Tests
- unit: existing Vitest suite must pass with zero regressions after migration
- contract: `npm run css:check` must exit 0; `npm run type-check` must exit 0 with src/qc-gate/**/* now included in tsconfig.json
- integration: none new — no route or API change
- E2E: none new — no behavioral change; existing `tests/e2e/test_qc_gate_e2e.py` is a read-only regression guard
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
- AC-1: `main.js` → `main.ts` with typed `createApp` call; `index.html` is left unchanged (Vite resolves `main.ts` automatically — per CLAUDE.md TypeScript Migration Rules)
- AC-2: `composables/useQcGateData.js` → `useQcGateData.ts` with explicit TypeScript types for all public return values (reactive refs, computed properties, and any API response interfaces); no bare `any` without `// TODO: type <reason>`
- AC-3: `App.vue` uses `<script setup lang="ts">` with typed reactive state and typed composable consumption; all stale `.js` import specifiers replaced with extension-free specifiers
- AC-4: `components/LotTable.vue` uses `<script setup lang="ts">` with typed `defineProps` for all props
- AC-5: `components/QcGateChart.vue` uses `<script setup lang="ts">` with typed `defineProps`; echarts click-handler callback parameter annotated with `// TODO: type echarts callback` (per CLAUDE.md TypeScript Migration Rules — known library gap)
- AC-6: No stale `.js` specifiers remain in any migrated file; all internal imports use extension-free specifiers (per CLAUDE.md TypeScript Migration Rules)
- AC-7: `tsconfig.json` include array expanded to cover `"src/qc-gate/**/*"` following the precedent of all prior Phase 3 migrations
- AC-8: `contracts/ci/ci-gate-contract.md` schema-version bumped to 1.3.8; `contracts/CHANGELOG.md` entry [ci 1.3.8] added documenting Phase 3 item #17 scope expansion
- AC-9: `npm run type-check` exits 0; `npm run build` exits 0; `npm run css:check` exits 0; `npm run test` exits 0

## Tasks Not Applicable
- not-applicable: 2.1, 2.3, 2.4, 2.5, 3.2, 3.3, 3.4, 3.5, 4.1, 4.3, 5.1, 5.2, 6.4

## Clarifications or Assumptions
- `index.html` references `./main.js` — do NOT update; Vite resolves `main.ts` correctly at build time. This is a cosmetic pre-existing pattern across all feature apps (per CLAUDE.md TypeScript Migration Rules).
- `style.css` is excluded from migration scope (no TypeScript content).
- `components/QcGateChart.vue` contains an echarts click handler; the callback parameter must receive a `// TODO: type echarts callback` annotation rather than blocking on precise library typings (per CLAUDE.md TypeScript Migration Rules).
- No Python parity tests (`tests/test_frontend_*_parity.py`) reference qc-gate files by path; no Python test changes are required for this migration.
- The qc-gate backend routes (`src/mes_dashboard/routes/qc_gate_routes.py`) and service (`services/qc_gate_service.py`) are unaffected — this change is purely frontend.
- API response interfaces for `useQcGateData.ts` should follow the typing pattern established in prior Phase 3 migrations (typed refs wrapping shapes from `core/api.ts`).
- The existing `tests/e2e/test_qc_gate_e2e.py` provides a read-only regression guard; no changes to it are required or expected.
- No shared barrel (`index.ts`) exists in qc-gate/ — unlike shared-ui/, this is a standalone feature app with no barrel file to audit.
- Current tsconfig.json include does not cover qc-gate/; this change adds it as item #13 in the include array (after src/resource-status/**/*).

## Context Manifest Draft

### Affected Surfaces
- `frontend/src/qc-gate/` (migration target — 5 files: main.js, App.vue, composables/useQcGateData.js, components/LotTable.vue, components/QcGateChart.vue)
- `frontend/tsconfig.json` (include array expansion)
- `contracts/ci/ci-gate-contract.md` (schema-version bump 1.3.7 → 1.3.8 + Gate Compatibility Note)
- `contracts/CHANGELOG.md` (new entry [ci 1.3.8])

### Allowed Paths
- specs/changes/migrate-qc-gate-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/qc-gate/
- frontend/src/core/
- frontend/src/shared-composables/
- frontend/tsconfig.json
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md

### Agent Work Packets

#### change-classifier
- specs/changes/migrate-qc-gate-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md

#### contract-reviewer
- specs/changes/migrate-qc-gate-ts/
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md
- frontend/tsconfig.json

#### test-strategist
- specs/changes/migrate-qc-gate-ts/
- frontend/src/qc-gate/

#### frontend-engineer
- specs/changes/migrate-qc-gate-ts/
- frontend/src/qc-gate/
- frontend/src/core/
- frontend/src/shared-composables/
- frontend/tsconfig.json

#### ci-cd-gatekeeper
- specs/changes/migrate-qc-gate-ts/
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md

#### qa-reviewer
- specs/changes/migrate-qc-gate-ts/
- frontend/src/qc-gate/
