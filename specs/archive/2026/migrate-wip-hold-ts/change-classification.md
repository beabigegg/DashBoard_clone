---
change-id: migrate-wip-hold-ts
classifier-version: 1
tier: 3
---

# Change Classification — migrate-wip-hold-ts

## Tier
- 3

## Change Type
pure-ts-migration

## Architecture Review Required
no

## Affected Surfaces
- frontend/src/wip-overview/
- frontend/src/wip-detail/
- frontend/src/hold-overview/
- frontend/src/hold-detail/

## Required Agents
- contract-reviewer
- frontend-engineer
- ci-cd-gatekeeper
- qa-reviewer

## Tasks Not Applicable
- 2.1 (API contract — no API surface change)
- 2.2 (CSS/UI contract — no styling change; enforced by css:check)
- 2.3 (Env contract — no env var change)
- 2.4 (Data shape contract — no data schema change)
- 2.5 (Business logic contract — no behavior change)
- 3.2 (Integration tests — pure TS migration)
- 3.3 (E2E/resilience tests — Tier 3)
- 3.4 (Data-boundary/monkey tests — Tier 3)
- 3.5 (Stress/soak tests — Tier 3)
- 4.1 (Backend — no Python/route/service changes)
- 4.3 (Env/deploy — no env/deploy changes)
- 5.1 (UI/UX review — no UI changes)
- 5.2 (Visual review — no visual changes)
- 6.4 (Nightly/weekly gates — Tier 3)

## Optional Artifacts
- current-behavior.md: no
- proposal.md: no
- spec.md: no
- design.md: no
- qa-report.md: yes
- regression-report.md: no

## Inferred Acceptance Criteria
AC-1: All four affected apps (wip-overview/, wip-detail/, hold-overview/, hold-detail/) have main.js renamed to main.ts, and every .vue file's <script> block uses lang="ts".
AC-2: `cd frontend && npm run type-check` (vue-tsc --noEmit) exits 0 with zero errors across the migrated surface.
AC-3: `cd frontend && npm run css:check` exits 0 — no CSS or design-token changes occurred.
AC-4: `cd frontend && npm run test` passes — all existing Vitest unit tests still pass with the migrated source.
AC-5: `cd frontend && npm run build` succeeds — Vite resolves the renamed main.ts entries from the existing index.html ./main.js references (per CLAUDE.md: index.html is NOT updated).
AC-6: No runtime behavior, API request/response shape, CSS class, or business logic changes — diff limited to type annotations, lang="ts", file rename, and necessary type-only imports.
AC-7: echarts callback parameters (notably in hold-overview/HoldTreeMap.vue) are annotated with `// TODO: type echarts callback` and do not block the migration.
AC-8: Imports referencing not-yet-fully-migrated barrels (wip-shared/, resource-shared/) drop the file extension rather than hard-coding .js or .ts.
AC-9: No Python parity test (tests/test_frontend_*_parity.py) references any .js path in the four migrated app directories.
AC-10: `cdd-kit gate migrate-wip-hold-ts --strict` exits clean.

## Contract Impact
No contract updates required. Existing type-check, css:check, and Vitest gates already cover the migrated surface; no new gate definitions needed.

- contracts/api/*: not affected
- contracts/business/*: not affected
- contracts/css/*: not affected (enforced by css:check)
- contracts/data/*: not affected
- contracts/env/*: not affected
- contracts/ci/ci-gate-contract.md: read-only confirmation only — no new entries

## Context Manifest Draft

### Affected Surfaces
- frontend/src/wip-overview/
- frontend/src/wip-detail/
- frontend/src/hold-overview/
- frontend/src/hold-detail/

### Allowed Paths
- specs/changes/migrate-wip-hold-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/wip-overview/
- frontend/src/wip-detail/
- frontend/src/hold-overview/
- frontend/src/hold-detail/
- frontend/src/core/
- frontend/src/shared-composables/
- frontend/src/shared-ui/
- frontend/src/wip-shared/
- frontend/src/resource-shared/
- frontend/tsconfig.json
- frontend/vite.config.ts
- frontend/vitest.config.js
- frontend/package.json
- frontend/scripts/
- frontend/tests/
- contracts/ci/ci-gate-contract.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/CHANGELOG.md

### Agent Work Packets

#### contract-reviewer
- specs/changes/migrate-wip-hold-ts/
- specs/context/contracts-index.md
- contracts/ci/ci-gate-contract.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/CHANGELOG.md

#### frontend-engineer
- specs/changes/migrate-wip-hold-ts/
- frontend/src/wip-overview/
- frontend/src/wip-detail/
- frontend/src/hold-overview/
- frontend/src/hold-detail/
- frontend/src/core/
- frontend/src/shared-composables/
- frontend/src/shared-ui/
- frontend/src/wip-shared/
- frontend/src/resource-shared/
- frontend/tsconfig.json
- frontend/vite.config.ts
- frontend/package.json
- frontend/tests/

#### ci-cd-gatekeeper
- specs/changes/migrate-wip-hold-ts/
- contracts/ci/ci-gate-contract.md
- frontend/package.json
- frontend/tsconfig.json
- frontend/vitest.config.js
- frontend/scripts/

#### qa-reviewer
- specs/changes/migrate-wip-hold-ts/
- frontend/src/wip-overview/
- frontend/src/wip-detail/
- frontend/src/hold-overview/
- frontend/src/hold-detail/
- frontend/tests/
