# Change Classification

## Change Types
- primary: TypeScript migration (rename .js → .ts, add lang="ts" to SFCs)
- secondary: audit and replace local useAutoRefresh.js (duplicate of shared-composables/useAutoRefresh.ts — replace with shared import or migrate in-place), fix all stale .js import specifiers, expand tsconfig.json include

## Risk Level
- low

## Impact Radius
- module-level (hold-history/ source files only; shared layers are read-only reference targets; no behavior change)

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
| qa-report.md | yes | release readiness evidence; useAutoRefresh.js audit decision (replace vs. migrate) warrants explicit per-AC record |
| regression-report.md | no | |

## Required Contracts
- API: none
- CSS/UI: css-contract.md — confirm no new violations (style.css not modified)
- Env: none
- Data shape: none
- Business logic: none
- CI/CD: ci-gate-contract.md — schema-version bump to 1.3.6 + Gate Compatibility Note for Phase 3 item #2; contracts/CHANGELOG.md entry [ci 1.3.6]

## Required Tests
- unit: existing Vitest suite (270+ tests) must pass with zero regressions
- contract: css:check must exit 0; npm run type-check must exit 0 scoped to hold-history/**/*
- (all others): none new — pure rename; no new behaviour to test

## Required Agents
- contract-reviewer
- test-strategist
- frontend-engineer
- ci-cd-gatekeeper
- qa-reviewer

## Inferred Acceptance Criteria
- AC-1: main.js → main.ts with typed createApp call; index.html left unchanged (Vite resolves main.ts automatically)
- AC-2: useAutoRefresh.js audit complete — decision recorded: either (a) deleted and App.vue updated to import from shared-composables/useAutoRefresh, or (b) renamed to useAutoRefresh.ts with typed parameters; no bare any without // TODO: type <reason>
- AC-3: useHoldHistoryDuckDB.js → useHoldHistoryDuckDB.ts with explicit TypeScript types for all public return values; DuckDB query result rows typed (pattern from useRejectHistoryDuckDB.ts applied)
- AC-4: App.vue uses `<script setup lang="ts">` with typed reactive state; all internal .js specifiers (useHoldHistoryDuckDB.js, useAutoRefresh.js) replaced with extension-free or .ts specifiers
- AC-5: All 8 component SFCs (DailyTrend.vue, DetailTable.vue, DurationChart.vue, FilterBar.vue, FilterIndicator.vue, ReasonPareto.vue, RecordTypeFilter.vue, SummaryCards.vue) use `<script setup lang="ts">` with typed defineProps
- AC-6: No stale .js specifiers remain in any migrated file; all internal imports use extension-free specifiers (per CLAUDE.md TypeScript Migration Rules)
- AC-7: tsconfig.json include expanded to cover src/hold-history/**/*
- AC-8: ci-gate-contract.md schema-version 1.3.6; contracts/CHANGELOG.md [ci 1.3.6] entry added documenting Phase 3 item #2 scope expansion
- AC-9: npm run type-check exits 0; npm run build exits 0; css:check exits 0
- AC-10: All 270+ existing Vitest tests pass (no regressions)
- AC-11: No bare `any` without `// TODO: type <reason>`; no new @ts-expect-error introduced unless justified with phase note
- AC-12: cdd-kit gate --strict passes

## Tasks Not Applicable
- not-applicable: 2.1, 2.3, 2.4, 2.5, 3.2, 3.3, 3.4, 3.5, 4.1, 4.3, 5.1, 5.2, 6.4

## Clarifications or Assumptions
- hold-history/useAutoRefresh.js is a local duplicate of wip-shared/composables/useAutoRefresh.ts (same logic: interval scheduling, document visibility pause, stale indicator). The frontend-engineer must audit whether to (a) delete it and redirect App.vue to shared-composables/useAutoRefresh, or (b) rename to .ts and type in place. Either path is acceptable; the decision must be recorded in qa-report.md.
- index.html references `./main.js` — do NOT update; Vite resolves main.ts correctly (per CLAUDE.md TypeScript Migration Rules and change-request.md guidance).
- style.css is excluded from migration scope (no TypeScript content).
- No Python parity tests reference hold-history files; no Python test changes required.
- portal-shell/nativeModuleRegistry.js and routeContracts.js reference '/hold-history' route strings — these are string constants, not file imports, and are not affected by this migration.
- Structural pattern for useHoldHistoryDuckDB.ts follows useRejectHistoryDuckDB.ts (Phase 3 item #1) — consult that file for DuckDB composable typing conventions.

## Context Manifest Draft

### Affected Surfaces
- frontend/src/hold-history/ (migration target — all 14 files)
- frontend/tsconfig.json (include array expansion)
- contracts/ci/ci-gate-contract.md (schema-version bump 1.3.5 → 1.3.6 + Gate Compatibility Note)
- contracts/CHANGELOG.md (new entry [ci 1.3.6])

### Allowed Paths
- specs/changes/migrate-hold-history-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/hold-history/
- frontend/src/reject-history/
- frontend/src/shared-composables/useAutoRefresh.ts
- frontend/src/wip-shared/composables/useAutoRefresh.ts
- frontend/tsconfig.json
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md

### Agent Work Packets

#### contract-reviewer
- specs/changes/migrate-hold-history-ts/
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md
- frontend/tsconfig.json

#### test-strategist
- specs/changes/migrate-hold-history-ts/
- frontend/src/hold-history/

#### frontend-engineer
- specs/changes/migrate-hold-history-ts/
- frontend/src/hold-history/
- frontend/src/shared-composables/useAutoRefresh.ts
- frontend/src/wip-shared/composables/useAutoRefresh.ts
- frontend/src/reject-history/
- frontend/tsconfig.json

#### ci-cd-gatekeeper
- specs/changes/migrate-hold-history-ts/
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md
- frontend/tsconfig.json

#### qa-reviewer
- specs/changes/migrate-hold-history-ts/
