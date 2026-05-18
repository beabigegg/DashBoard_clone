---
change-id: migrate-mid-section-defect-ts
schema-version: 0.1.0
last-changed: 2026-05-18
---

# Implementation Plan: migrate-mid-section-defect-ts

## Objective

Migrate `frontend/src/mid-section-defect/` from JavaScript to TypeScript (Phase 3): rename the two `.js` entries to `.ts`, add type annotations sufficient to pass `vue-tsc --noEmit` under `strict: true`, expand `frontend/tsconfig.json` `include`, and bump `contracts/ci/ci-gate-contract.md` 1.3.13 → 1.3.14 with a matching `contracts/CHANGELOG.md` entry. No behavior, no UI, no contract surface changes beyond the procedural CI patch bump.

## Execution Scope

### In Scope
- Rename `frontend/src/mid-section-defect/main.js → main.ts`.
- Migrate `<script setup>` block in `frontend/src/mid-section-defect/App.vue` to `<script setup lang="ts">` and add TypeScript types (this is the only substantive type work in the change).
- Drop `.js` extensions from in-app cross-feature import specifiers inside `App.vue` and `components/SuspectContextPanel.vue` (5 specifiers total; do NOT rename them to `.ts`).
- Expand `frontend/tsconfig.json` `include` with `"src/mid-section-defect/**/*"`.
- Bump `contracts/ci/ci-gate-contract.md` schema-version 1.3.13 → 1.3.14 and add `### frontend-type-check scope expansion (Phase 3 — migrate-mid-section-defect-ts)` subsection.
- Add matching `[ci 1.3.14]` entry to `contracts/CHANGELOG.md`.
- Audit Python tests under `tests/**/*.py` and Vitest tests under `frontend/tests/legacy/` for any hardcoded `mid-section-defect/*.js` path references (audit-only; no expected repairs — see Audit Checklist).

### Out of Scope
- `frontend/src/mid-section-defect/index.html` — `./main.js` Vite entry MUST NOT be modified (Vite resolves `main.ts` at build time per CLAUDE.md Phase 3 rule; AC-8).
- Any change to `frontend/src/shared-ui/components/MultiSelect.vue` prop/emit surface (consumed by 9 apps; any addition must be additive — none planned here; AC-6).
- Any change to component `.vue` files other than the import-specifier extension drop in `SuspectContextPanel.vue` (`AnalysisSummary.vue`, `DetailTable.vue`, `FilterBar.vue`, `KpiCards.vue`, `ParetoChart.vue`, `TrendChart.vue` are not touched).
- `style.css` — no changes.
- Backend (`src/mes_dashboard/`), worker, contract surface beyond the ci patch bump.
- No new tests added; no test file renames (`mid-section-defect-composables.test.js` and `msd-completeness-warning.test.js` remain `.js`).

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | `frontend/src/mid-section-defect/main.js` | Rename to `main.ts`. Body is 4 lines (`createApp(App).mount('#app')`); add types only if needed for `strict`. | frontend-engineer |
| IP-2 | `frontend/src/mid-section-defect/App.vue` | Change `<script setup>` → `<script setup lang="ts">`. Add types for reactive state (`filters`, `committedFilters`, `analysisData`, `detailData`, `detailPagination`, `loading`, `stationOptions`, `availableLossReasons`, `resolutionInfo`, `currentTraceQueryId`, `suspectPanelMachine`, `restoredFromCache`, `queryError`, `hasQueried`, `queryMode`, `containerInputType`, `containerInput`), helper-function parameters (`buildMaterialChartFromAttribution`, `buildMachineChartFromAttribution`, `loadDetail(page, signal)`, `handleMachineBarClick`, `createAbortSignal`, `toDateString`, `handleUpdateFilters`), and `_abortControllers: Map<string, AbortController>`. Drop `.js` from the 4 cross-feature import specifiers (`../core/api.js`, `../core/unwrap-api-result.js`, `../shared-composables/useFilterOrchestrator.js`, `../shared-composables/useTraceProgress.js`). | frontend-engineer |
| IP-3 | `frontend/src/mid-section-defect/components/SuspectContextPanel.vue` | Drop `.js` from `import { apiGet } from '../../core/api.js'` → `'../../core/api'`. No other change. | frontend-engineer |
| IP-4 | `frontend/tsconfig.json` | Append `"src/mid-section-defect/**/*"` to the `include` array (exact diff below). | frontend-engineer |
| IP-5 | `contracts/ci/ci-gate-contract.md` | Update front-matter `schema-version: 1.3.13 → 1.3.14`, update `last-changed: 2026-05-18`, and append `### frontend-type-check scope expansion (Phase 3 — migrate-mid-section-defect-ts)` subsection after the migrate-material-trace-ts block (current line 136). | frontend-engineer |
| IP-6 | `contracts/CHANGELOG.md` | Prepend `## [ci 1.3.14] — 2026-05-18` entry above the existing `[ci 1.3.13]` block (line 11) noting `mid-section-defect/**/*` added to `tsconfig.json include`. | frontend-engineer |
| IP-7 | `tests/**/*.py`, `frontend/tests/legacy/*.js` | Run grep audit; confirm `grep -r "mid-section-defect.*\.js" tests/` returns empty (already verified during planning — expected no-op). | frontend-engineer |

## Source Artifact Pointers

| source | relevant pointer | used for |
|---|---|---|
| `specs/changes/migrate-mid-section-defect-ts/change-classification.md` | §Inferred Acceptance Criteria (AC-1 … AC-8) | scope and required outcomes |
| `specs/changes/migrate-mid-section-defect-ts/test-plan.md` | full Acceptance Criteria → Test Mapping; §Gate Commands | tests/commands the implementation must pass |
| `specs/changes/migrate-mid-section-defect-ts/ci-gates.md` | §Required Gates table; §Promotion Policy | merge-eligibility gates |
| `CLAUDE.md` | §TypeScript Migration Rules; §Shared UI Component Notes (MultiSelect) | migration mechanics and SFC-shared-component guardrails |
| `contracts/ci/ci-gate-contract.md` lines 130–136 | migrate-material-trace-ts subsection (Phase 3 precedent) | exact prose template for the new 1.3.14 subsection |
| `contracts/CHANGELOG.md` lines 11–14 | `[ci 1.3.13]` entry | template for the new `[ci 1.3.14]` entry |

## File-Level Plan

### File Inventory (every file in `frontend/src/mid-section-defect/`)

| path | classification | action |
|---|---|---|
| `main.js` | rename to .ts | rename → `main.ts`; trivial body, no type signatures needed |
| `App.vue` | edit-in-place | add `<script setup lang="ts">`; type all reactive state and helpers; drop `.js` from 4 cross-feature import specifiers |
| `index.html` | keep as-is | MUST NOT modify `./main.js` Vite entry (AC-8) |
| `style.css` | keep as-is | no changes |
| `components/AnalysisSummary.vue` | keep as-is | no `.js` imports; no `lang="ts"` switch in scope |
| `components/DetailTable.vue` | keep as-is | same |
| `components/FilterBar.vue` | keep as-is | same |
| `components/KpiCards.vue` | keep as-is | same |
| `components/ParetoChart.vue` | keep as-is | same |
| `components/SuspectContextPanel.vue` | edit-in-place | drop `.js` from single `apiGet` import specifier; no other change |
| `components/TrendChart.vue` | keep as-is | no `.js` imports |

(There are no `composables/`, `services/`, or `utils/` subdirectories in this app.)

### Files outside the app

| path or glob | action | notes |
|---|---|---|
| `frontend/tsconfig.json` | edit-in-place | see exact diff below |
| `contracts/ci/ci-gate-contract.md` | edit-in-place | front-matter bump + new subsection (see §Contract Updates) |
| `contracts/CHANGELOG.md` | edit-in-place | prepend new `[ci 1.3.14]` entry (see §Contract Updates) |
| `frontend/src/mid-section-defect/index.html` | MUST NOT change | AC-8 enforces zero diff |
| `frontend/src/shared-ui/components/MultiSelect.vue` | MUST NOT change | AC-6 enforces zero diff (shared by 9 apps) |
| `tests/**/*.py` | audit-only | grep audit, no edits expected |
| `frontend/tests/legacy/mid-section-defect-composables.test.js` | audit-only | inlines logic; no rename, no `.js` specifier update |
| `frontend/tests/legacy/msd-completeness-warning.test.js` | audit-only | inlines logic; no rename, no `.js` specifier update |

### Exact `tsconfig.json` diff

**Before** (line 19, end of `include` array):
```
..., "src/production-history/**/*", "src/query-tool/**/*", "src/material-trace/**/*"]
```

**After** (append one entry, directory-level path per CLAUDE.md):
```
..., "src/production-history/**/*", "src/query-tool/**/*", "src/material-trace/**/*", "src/mid-section-defect/**/*"]
```

## Contract Updates

- **API**: none.
- **CSS/UI**: none.
- **Env**: none.
- **Data shape**: none.
- **Business logic**: none.
- **CI/CD**:
  - `contracts/ci/ci-gate-contract.md` front-matter: `schema-version: 1.3.13` → `1.3.14`; `last-changed: 2026-05-14` → `2026-05-18`.
  - Append new subsection after current line 136 (after migrate-material-trace-ts block):

    ```md
    ### frontend-type-check scope expansion (Phase 3 — migrate-mid-section-defect-ts)

    - **Before this change**: `tsconfig.json` `include` covered `core/`, `shared-composables/`, `shared-ui/`, `admin-shared/`, `resource-shared/`, `wip-shared/`, `reject-history/`, `hold-history/`, `wip-overview/`, `wip-detail/`, `hold-overview/`, `hold-detail/`, `resource-status/`, `qc-gate/`, `resource-history/`, `job-query/`, `production-history/`, `query-tool/`, `material-trace/`.
    - **From this change onward**: `include` gains `"src/mid-section-defect/**/*"`, covering `main.ts` and `App.vue` (with `<script setup lang="ts">`) under `strict: true`.
    - **Gate tier unchanged**: informational (continue-on-error: true). Promotion follows the standard Informational Gate Promotion Policy.
    - **Schema-version bump to 1.3.14 (patch)**: additive prose only — gate tier, command, and status are unchanged.
    - **Source**: change `migrate-mid-section-defect-ts`.
    ```

  - `contracts/CHANGELOG.md`: prepend (above the `[ci 1.3.13]` block at line 11):

    ```md
    ## [ci 1.3.14] — 2026-05-18
    ### Changed
    - migrate-mid-section-defect-ts (Phase 3): `tsconfig.json` `include` expanded with `"src/mid-section-defect/**/*"`, covering `main.ts` and `App.vue` under `strict: true`. Gate tier unchanged (informational). Additive prose only.
    - Source: change `migrate-mid-section-defect-ts`.
    ```

## Audit Checklist

Run before declaring complete; all four must pass:

1. **Python `.js` path audit**:
   `grep -r "mid-section-defect.*\.js" tests/` → must return empty.
   (Verified during planning: 19 Python test files mention `mid-section-defect` / `mid_section_defect` but none reference `.js` paths.)
2. **Vitest test audit**:
   `grep -nE "vi\.mock|require\(|import\(" frontend/tests/legacy/mid-section-defect-composables.test.js frontend/tests/legacy/msd-completeness-warning.test.js` → must return empty (already verified — neither file uses `vi.mock`, `require()`, or dynamic `import()`; both inline their logic via static `import`). No changes required to these test files.
3. **`index.html` no-change audit (AC-8)**:
   `git diff HEAD -- frontend/src/mid-section-defect/index.html` → must show zero changes.
4. **MultiSelect surface audit (AC-6)**:
   `git diff HEAD -- frontend/src/shared-ui/components/MultiSelect.vue` → must show zero changes.

## Test Execution Plan

See `specs/changes/migrate-mid-section-defect-ts/test-plan.md` for the full AC → test mapping. Gate commands (run in this order from repo root):

| acceptance criterion | test / command | expected signal |
|---|---|---|
| AC-1, AC-3 | `cd frontend && npm run test` | exits 0; both legacy test files green |
| AC-2 | `cd frontend && npm run type-check` | exits 0 with zero vue-tsc errors after `tsconfig.json include` expansion |
| AC-4 | `pytest tests/ -m "not e2e"` | exits 0 |
| AC-4 (audit) | `grep -r "mid-section-defect.*\.js" tests/` | empty output |
| AC-5 | `cdd-kit validate` | exits 0; `ci-gate-contract.md` schema-version == 1.3.14; `CHANGELOG.md` has matching `[ci 1.3.14]` entry |
| AC-6 | `git diff HEAD -- frontend/src/shared-ui/components/MultiSelect.vue` | zero diff |
| AC-7 | grep `import('...mid-section-defect.*\.js')` inside `frontend/src/` | empty (no dynamic imports targeting renamed files) |
| AC-8 | `git diff HEAD -- frontend/src/mid-section-defect/index.html` | zero diff |
| CSS governance | `cd frontend && npm run css:check` | exits 0 |

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.
- Do NOT modify `frontend/src/mid-section-defect/index.html` under any circumstance (AC-8).
- Do NOT update `vi.mock('...file.js')` static specifiers (CLAUDE.md rule). None exist in the two legacy test files today; this is a preventive no-op constraint.
- Do NOT add a `.test.ts` SFC-paired test (none planned; would require separate `vitest.config.js` verification).
- Do NOT rename or modify the components listed as "keep as-is" in §File Inventory.

## Non-Goals (what NOT to do)

- Do NOT rename test files (`mid-section-defect-composables.test.js`, `msd-completeness-warning.test.js`) to `.ts`.
- Do NOT switch `lang="ts"` on the 7 unchanged `.vue` components — out of scope.
- Do NOT introduce `any` or `as any`; use the wrap-with-interface + `// @ts-expect-error <phase note>` + double-cast pattern from CLAUDE.md when wrapping a not-yet-migrated `.js` module.
- Do NOT touch any path outside the manifest's Allowed Paths. If type-checking surfaces a strict-mode error in a shared module (e.g., `useTraceProgress`), do NOT fix it inline — declare a local interface and cast at the call site.
- Do NOT modify `frontend/vitest.config.js` (it already covers `src/**/*.test.ts` from prior migrations; no SFC-paired test is being added).

## Known Risks

- **Type-checking newly-typed App.vue under `strict: true`** may surface errors from cross-feature imports (`useFilterOrchestrator`, `useTraceProgress`, shared-ui components, `apiGet`, `unwrapApiResult`). Those modules are already migrated to TS (per CLAUDE.md Phase 1b/1c/2 status), so most types should flow through. If a strict-mode error arises from a still-`.js` consumer surface, use the wrap-with-interface + `// @ts-expect-error <phase note>` + double-cast pattern from CLAUDE.md, not `as any`.
- **echarts callback parameters** (any `params` in formatter/tooltip handlers passed through to `ParetoChart` / `TrendChart` from `App.vue`) must be annotated `// TODO: type echarts callback` per CLAUDE.md; do not block migration on these.
- **MultiSelect.vue is shared by 9 apps**; the current plan does NOT modify it. If a strict-mode prop-type mismatch surfaces, any fix must be additive (optional prop/emit) and grep-audited across all 9 consumers before merge.
- **Reactive state shape**: `analysisData` is loosely shaped (`kpi: {}`, `charts: {}`, `attribution`, `materials_attribution`, `daily_trend`, `genealogy_status`, `total_ancestor_count`); declare an explicit interface (e.g., `MsdAnalysisData`) rather than letting `ref({} as any)` leak through. Document any tightening in `agent-log/frontend-engineer.yml`.
- **`buildDetailParams()` references `snapshot.containerValues`** but the non-container branch of `snapshotFilters()` may produce a snapshot without that field. Type-strictening will surface this — model `CommittedFilters` as a discriminated union on `queryMode`, or mark `containerValues?: string[]` optional, to preserve current runtime behavior.

