---
change-id: migrate-material-trace-ts
schema-version: 0.1.0
last-changed: 2026-05-18
---

# Implementation Plan: migrate-material-trace-ts

## Objective

Migrate the `material-trace` feature app from JavaScript to TypeScript following the established Phase 3 per-app pattern: rename the 7-line `main.js` entry to `main.ts`, convert `App.vue` to `<script setup lang="ts">` with appropriate type annotations, drop the `.js` extension from already-migrated core imports, and add the app's source glob to `tsconfig.json`. No behavior change, no template change, no CSS change.

## Execution Scope

### In Scope
- Rename `frontend/src/material-trace/main.js` to `frontend/src/material-trace/main.ts` (contents unchanged).
- Convert `frontend/src/material-trace/App.vue` `<script setup>` block to `<script setup lang="ts">` with type annotations on `ref<T>()` declarations, function parameters, inline body objects, and template event handler casts.
- Drop the `.js` extension from these two import specifiers inside `App.vue`:
  - `../core/api.js` → `../core/api`
  - `../core/reject-history-filters.js` → `../core/reject-history-filters`
- Append `"src/material-trace/**/*"` to the `include` array in `frontend/tsconfig.json`.

### Out of Scope
- Do NOT modify `frontend/src/material-trace/index.html` — keep `./main.js` reference; Vite resolves `main.ts` at build time (established cross-app convention; see CLAUDE.md TS Migration Rules).
- Do NOT modify `frontend/src/material-trace/style.css` or any template markup; no behavior, layout, or i18n change.
- Do NOT modify shared-ui component imports (`../shared-ui/components/*.vue`) — already extension-free and resolve via Vite SFC handling.
- Do NOT modify `frontend/tests/legacy/material-trace-composables.test.js` or `frontend/tests/validation/useMaterialTrace.validation.test.js`. Both import only from `core/` modules and must continue to pass untouched.
- Do NOT modify `tests/e2e/test_material_trace_e2e.py` (browser-driven, extension-independent).
- Do NOT modify `frontend/vitest.config.js` — `src/**/*.test.ts` pattern is already present (no SFC-paired test is being added in this change).
- Do NOT introduce new behavior, refactors, prop/emit changes, or gratuitous `as any` escapes.
- Do NOT touch any other feature app, shared module, or backend code.

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | `frontend/src/material-trace/main.js` | Rename file to `main.ts` via `git mv`; contents unchanged (7 lines: `createApp(App).mount('#app')` plus two CSS side-effect imports). | frontend-engineer |
| IP-2 | `frontend/src/material-trace/App.vue` | Change opening tag to `<script setup lang="ts">`; add type annotations per "App.vue Type Annotation Map" below; drop `.js` from `../core/api.js` and `../core/reject-history-filters.js` import specifiers. | frontend-engineer |
| IP-3 | `frontend/tsconfig.json` | Append `"src/material-trace/**/*"` to the `include` array (preserve existing entries and order). | frontend-engineer |

## Source Artifact Pointers

| source | relevant pointer | used for |
|---|---|---|
| change-classification.md | Inferred Acceptance Criteria AC-1..AC-8 | acceptance scope; agent ownership |
| test-plan.md | "Acceptance Criteria — Test Mapping" table; "Tests That Must Fail Before Implementation" | gating commands and pre-impl failure expectations |
| ci-gates.md | "Required Gates for This Change" table | Tier 1 gate commands (type-check, build, unit, css:check) |
| ci-gates.md | "Rollback Policy" | no parquet/Redis cleanup required (query-tool-style on-demand) |
| context-manifest.md | "Allowed Paths" | read boundary for all agents |
| CLAUDE.md | "TypeScript Migration Rules" section | mandatory migration constraints (see Handoff Constraints) |
| contracts/ci/ci-gate-contract.md | schema-version 1.3.13 (`"src/material-trace/**/*"` include note) | contract alignment for tsconfig scope expansion (already landed) |

## File-Level Plan

| path or glob | action | notes |
|---|---|---|
| `frontend/src/material-trace/main.js` | rename → `main.ts` | Same 7 lines; do not edit content. Use `git mv` to preserve history. |
| `frontend/src/material-trace/App.vue` | edit | `<script setup>` → `<script setup lang="ts">`; drop `.js` on the two `../core/*` imports; add type annotations per map below. No template/style changes beyond the single `($event.target as HTMLSelectElement).value` cast required for strict template typing. |
| `frontend/src/material-trace/index.html` | UNCHANGED | Keep `./main.js` reference; intentional per established Vite resolution pattern. |
| `frontend/src/material-trace/style.css` | UNCHANGED | No CSS change in this migration. |
| `frontend/tsconfig.json` | edit | Append `"src/material-trace/**/*"` to `include` array (after existing app entries). |
| `frontend/tests/legacy/material-trace-composables.test.js` | UNCHANGED | Imports only `core/` modules; must still pass under `npm run test:legacy`. |
| `frontend/tests/validation/useMaterialTrace.validation.test.js` | UNCHANGED | Imports only `core/` modules; must still pass under `npm run test`. |

### App.vue Type Annotation Map (concrete guidance for frontend-engineer)

Apply these annotations in `App.vue` `<script setup lang="ts">`. Reference types live in `frontend/src/core/api.ts` (`ApiResponse`, `FetchOptions`, `apiGet<T>`, `apiPost<T>`) and `frontend/src/core/reject-history-filters.ts` (`parseMultiLineInput(text: string | null | undefined): string[]`).

| symbol | declared type |
|---|---|
| `queryMode` | `ref<'forward' \| 'reverse'>('forward')` |
| `forwardInputType` | `ref<'lot' \| 'workorder'>('lot')` |
| `inputText` | `ref<string>('')` |
| `workcenterGroupOptions` | `ref<string[]>([])` |
| `selectedWorkcenterGroups` | `ref<string[]>([])` |
| `workcenterDropdownOpen` | `ref<boolean>(false)` |
| `workcenterSearch` | `ref<string>('')` |
| `rows` | `ref<Record<string, unknown>[]>([])` (rows are dynamic API payloads keyed by `TABLE_COLUMNS[*].key`) |
| `pagination` | `ref<Pagination>({ ... })` — declare a local `interface Pagination { page: number; per_page: number; total: number; total_pages: number }` and reuse it for reset-default literals in `clearResults` and the `executePrimaryQuery` failure paths |
| `loading` / `paginationLoading` | `ref<boolean>(false)` |
| `errorMessage` / `warningMessage` / `unresolvedWarning` | `ref<string>('')` |
| `currentQueryHash` | `ref<string \| null>(null)` |
| `pollingJobId` | `ref<string \| null>(null)` |
| `_pollingTimer` | `let _pollingTimer: ReturnType<typeof setTimeout> \| null = null` |
| `_pollingAttempts` | `let _pollingAttempts = 0` (inference acceptable) |
| `TABLE_COLUMNS` | `const TABLE_COLUMNS: { key: string; label: string }[] = [...]` |
| `switchQueryMode(mode)` | `mode: 'forward' \| 'reverse'` |
| `switchForwardInputType(type)` | `type: 'lot' \| 'workorder'` |
| `toggleWorkcenterGroup(group)` | `group: string` |
| `_startPolling(jobId, queryPage)` | `jobId: string, queryPage: number` |
| `executePrimaryQuery(page, opts)` | `page: number = 1, opts: { paginationOnly?: boolean; _fromPoll?: boolean } = {}` |
| `goToPage(page)` | `page: number` |
| `buildQualityWarning(qualityMeta, fallbackMeta)` | declare a local `interface QualityMeta { status?: string; max_rows?: number \| string \| null }`; `qualityMeta?: QualityMeta \| null, fallbackMeta?: QualityMeta \| null` |
| `apiGet` / `apiPost` call sites | call as `apiGet<MaterialTraceFilterOptions>(...)`, `apiPost<MaterialTraceQueryPayload>(...)`, `apiGet<MaterialTraceJobStatus>(...)`. Declare these interfaces locally — include only fields actually accessed: `workcenter_groups`; `rows`, `pagination`, `meta?.unresolved`, `quality_meta`, `query_hash`, `async`, `job_id`; `status`, `error`. Returned promise type is `Promise<ApiResponse<T>>`; existing `result.success`, `result.error?.message`, `result.data` access patterns survive unchanged. |
| Inline `body` in `executePrimaryQuery` | `const body: { mode: string; values: string[]; page: number; per_page: number; workcenter_groups?: string[] } = { ... }` |
| Inline `body` in `exportCsv` | `const body: { mode: string; values: string[]; workcenter_groups?: string[]; query_hash?: string } = { ... }` |
| `onDocumentClick(e)` | `e: MouseEvent`; inside, use `(e.target as HTMLElement \| null)?.closest('.multi-select')` |
| Template `@change="switchForwardInputType($event.target.value)"` | change to `@change="switchForwardInputType(($event.target as HTMLSelectElement).value)"` to satisfy strict template-expression typing |
| `catch (err)` blocks | annotate as `catch (err)`; access via `(err as Error)?.message` or narrow with `instanceof Error`; do not use `as any` |

Notes:
- No echarts usage in this app — no `// TODO: type echarts callback` markers required.
- All shared-ui imports already resolve via their `.vue` files; do not touch them.
- No `.js` files outside `core/` are imported by this app, so no `@ts-expect-error <phase note>` placeholders are expected. If any unmigrated `.js` dependency surfaces during implementation, follow the CLAUDE.md pattern (declare local interface → `@ts-expect-error <phase note>` → typed cast) and stop to confirm scope before continuing.

## Contract Updates

- API: none.
- CSS/UI: none.
- Env: none.
- Data shape: none.
- Business logic: none.
- CI/CD: already complete — `contracts/ci/ci-gate-contract.md` schema-version 1.3.13 records the `"src/material-trace/**/*"` tsconfig include addition. No further contract edit required in this change.

## Test Execution Plan

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 (main.js → main.ts, no behavior change) | `cd frontend && npm run test:legacy` (drives `frontend/tests/legacy/material-trace-composables.test.js`) | pass — node `--experimental-strip-types` resolves the import chain |
| AC-2 (App.vue `lang="ts"`, no banned `as any`) | `cd frontend && npm run type-check` | zero new vue-tsc errors; PR review verifies no gratuitous `as any` |
| AC-3 (import specifiers drop `.js`) | `cd frontend && npm run type-check` | compile-time resolution succeeds without the dropped extensions |
| AC-4 (index.html unchanged) | PR diff review | no hunk on `frontend/src/material-trace/index.html` |
| AC-5 (type-check passes, zero new errors) | `cd frontend && npm run type-check` | exit 0 with no new errors attributable to material-trace |
| AC-6 (build succeeds, material-trace bundle produced) | `cd frontend && npm run build` | exit 0; `dist/material-trace.html` (and its hashed assets) produced |
| AC-7 (existing test files pass) | `cd frontend && npm run test` + `cd frontend && npm run test:legacy` | both green, including `useMaterialTrace.validation.test.js` |
| AC-8 (css:check passes) | `cd frontend && npm run css:check` | exit 0 |

Pre-implementation failure check (per test-plan.md §"Tests That Must Fail Before Implementation"): `npm run test:legacy` is the canonical regression sentinel — it must be green before the rename and remain green after, since a broken import chain would surface there immediately. `npm run type-check` becomes meaningful only after `App.vue` gains `lang="ts"`.

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked` rather than expanding scope.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.
- Follow CLAUDE.md "TypeScript Migration Rules" exactly:
  - Do NOT update `index.html`'s `./main.js` reference.
  - Do NOT update any static `vi.mock('....js')` specifiers (none expected in scope; both existing test files import only from `core/`).
  - Audit every `.js` import specifier inside the migrated SFC. Drop the extension when the target is already `.ts`; do NOT rename specifiers to `.ts` — let Vite/TS resolve.
  - Use `git mv` for the `main.js → main.ts` rename to preserve history.
  - Prefer locally declared interfaces + `// @ts-expect-error <phase note>` + typed cast over `as any` if any unmigrated `.js` dependency surfaces.
- After implementation, run all four Tier 1 gate commands locally before opening PR: `npm run type-check`, `npm run build`, `npm run test` (plus `npm run test:legacy`), `npm run css:check`.

## Known Risks

- `vue-tsc` strict template-expression typing flags `$event.target.value` on `<select>`; the annotation map pre-resolves this with an `HTMLSelectElement` cast in the template.
- `pagination.value?.total_pages` arithmetic in `goToPage` passes through `Number(...)` already — after typing the `pagination` ref, confirm no `unknown` leak in `total_pages > 1` template comparisons.
- `apiGet` / `apiPost` return `Promise<ApiResponse<T>>`; existing code reads `result.success`, `result.error?.message`, `result.data`. Ensure local payload interfaces map to `ApiResponse<T>`'s `data` field, not the top-level response.
- The polling chain accesses `res?.data?.status` and `res?.data?.error`. `res` should be typed as `ApiResponse<MaterialTraceJobStatus>`; the local `MaterialTraceJobStatus` interface must include `status?: string` and `error?: string`.
- CI installs `contract-driven-delivery` without a version pin. If a newer cdd-kit release adds artifact requirements between plan-write and PR, re-run `cdd-kit validate` locally before merge.
