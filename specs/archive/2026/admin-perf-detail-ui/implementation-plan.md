---
change-id: admin-perf-detail-ui
schema-version: 0.1.0
last-changed: 2026-05-19
---

# Implementation Plan: admin-perf-detail-ui

## Objective

Render the 6 additive fields already returned by `GET /admin/api/performance-detail`
(see `contracts/api/api-contract.md` line ~290–292, recorded by the merged
`fix-admin-dashboard` change) inside the admin-dashboard SPA, so that admin users see
Redis eviction / slowlog telemetry and DuckDB memory / temp-dir telemetry without
regressing any existing rendering and without modifying any contract file (AC-8).

Concrete deliverables:

- Redis section in `frontend/src/admin-dashboard/tabs/CacheTab.vue` displays
  `evicted_keys`, `expired_keys`, `mem_fragmentation_ratio` (toFixed(2)), and a
  slowlog list of `{command, duration_us}` entries.
- A new DuckDB SectionCard in `frontend/src/admin-dashboard/tabs/PerformanceTab.vue`
  displays `temp_dir_bytes` (human-readable) and `memory_limit_state` (string).
- Any null/undefined field renders the literal placeholder `N/A`. A null or empty
  `slowlog` array renders one graceful `N/A` placeholder line (no list items).
- `usePerfDetail()` in `frontend/src/admin-shared/composables/useAdminData.ts`
  returns a typed `PerfDetailData` instead of `unknown`. The type is additive —
  every field already read by PerformanceTab / CacheTab / WorkerTab continues to
  type-check.
- 10 failing Vitest cases in `frontend/src/admin-dashboard/tabs/__tests__/PerfDetail.test.ts`
  precede every rendering / typing change (TDD).

## Execution Scope

### In Scope
- Create `frontend/src/admin-dashboard/tabs/__tests__/PerfDetail.test.ts` with the
  10 cases enumerated in test-plan.md (AC-1 .. AC-7). Tests must fail before any
  implementation lands.
- Add additive TS interfaces in `frontend/src/admin-shared/composables/useAdminData.ts`:
  `PerfDetailSlowlogEntry`, `PerfDetailRedis`, `PerfDetailDuckDB`, `PerfDetailData`.
  Change `usePerfDetail(): DataFetcher<unknown>` → `DataFetcher<PerfDetailData>`.
  `PerfDetailData` must be a superset of every field currently read by the three
  consuming tabs (`db_pool`, `direct_connections`, `redis` (with existing
  `used_memory`, `used_memory_human`, `peak_memory`, `peak_memory_human`,
  `maxmemory`, `maxmemory_human`, `connected_clients`, `hit_rate`, `namespaces`),
  `route_cache`, `process_caches`) plus the new `duckdb` sub-object.
- Additive markup in `frontend/src/admin-dashboard/tabs/CacheTab.vue`:
  - Append three new `SummaryCard`s for `evicted_keys`, `expired_keys`, and
    `mem_fragmentation_ratio` to the existing Redis `SummaryCardGroup`
    (the one already containing 已使用 / 峰值 / 連線數 / 命中率, lines ~103–108).
  - Add a slowlog list block (a `<ul>` of `<li>{command} — {duration_us}μs`) below
    the existing namespaces `DataTable` inside the same Redis `SectionCard`.
- Additive markup in `frontend/src/admin-dashboard/tabs/PerformanceTab.vue`:
  - New `SectionCard` titled "DuckDB" placed after the existing 連線池 SectionCard,
    rendering `temp_dir_bytes` (via inline `formatBytes` helper) and
    `memory_limit_state`. Section is `v-if="perfDetail?.duckdb"`; when the backend
    reports `data.duckdb === null` the section is skipped entirely (consistent with
    the existing `v-if="perfDetail?.redis"` pattern in CacheTab).
- Pure helpers (`formatBytes`, ratio formatter) co-located in the component's
  `<script setup>` block — no new shared utility file.
- Run and pass the local gate set from ci-gates.md: `npm run test -- --run`,
  `npm run css:check`, `npm run type-check` (informational), `cdd-kit validate`.

### Out of Scope
- Any modification to files under `contracts/` (AC-8). `contracts/css/css-inventory.md`
  was already bumped to v1.2.2 by a prior task and is NOT touched again.
- Any backend Python change (`src/mes_dashboard/**`).
- Any new API endpoint or any change to existing payload shape.
- Refactoring or restyling of any field already rendered by PerformanceTab,
  CacheTab, WorkerTab, OverviewTab, LogsTab, or UsageTab (AC-7: additive only).
- New shared-ui components, new Tailwind tokens, or new authored CSS. If a render
  rule cannot be expressed with existing tokens + shared-ui primitives, STOP and
  report `blocked` — touching `style.css` would force a `css-inventory.md` re-bump
  and violate AC-8 as currently scoped.
- Touching `frontend/src/admin-pages/`, `frontend/src/admin-user-usage-kpi/`, or
  any other SPA. The performance-detail view is exclusively in admin-dashboard
  (confirmed by grep for `/admin/api/performance-detail`, `usePerfDetail`,
  `evicted_keys`, `slowlog`).
- E2E / Playwright, visual-regression snapshots, integration tests against the
  live endpoint, resilience / soak / stress (per change-classification.md).
- Renaming the `frontend-unit-tests` job in `.github/workflows/frontend-tests.yml`
  (branch protection depends on this exact name).

## Required Changes

| id   | area                              | required action                                                                                                                                                                                                       | owner agent       |
|------|-----------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------|
| IP-1 | frontend tests (TDD)              | Create `frontend/src/admin-dashboard/tabs/__tests__/PerfDetail.test.ts` with all 10 cases from test-plan.md. Mount CacheTab and PerformanceTab via `@vue/test-utils`; stub the composables (or `apiGet`) to inject fixture payloads. Land in a failing state before IP-2 .. IP-4. | frontend-engineer |
| IP-2 | TS typing for `usePerfDetail`     | In `frontend/src/admin-shared/composables/useAdminData.ts`, add `PerfDetailSlowlogEntry`, `PerfDetailRedis`, `PerfDetailDuckDB`, `PerfDetailData`. Switch `usePerfDetail` return type to `DataFetcher<PerfDetailData>`. All new fields nullable; all existing fields preserved as a superset. | frontend-engineer |
| IP-3 | CacheTab Redis rendering          | Edit `frontend/src/admin-dashboard/tabs/CacheTab.vue`: append three `SummaryCard`s (`evicted_keys`, `expired_keys`, `mem_fragmentation_ratio` formatted via `toFixed(2)`) to the existing Redis `SummaryCardGroup`. Add a slowlog `<ul>` list (one `<li>` per entry) below the namespaces `DataTable`, with `N/A` placeholder when null or empty. No removal or reordering of existing markup. | frontend-engineer |
| IP-4 | PerformanceTab DuckDB rendering   | Edit `frontend/src/admin-dashboard/tabs/PerformanceTab.vue`: add a new `SectionCard` (header "DuckDB", `v-if="perfDetail?.duckdb"`) after the existing 連線池 SectionCard, with two `SummaryCard`s for `temp_dir_bytes` (formatted via inline `formatBytes`) and `memory_limit_state` (string passthrough, `N/A` when null). No changes to chart, refresh, or pool rendering. | frontend-engineer |
| IP-5 | Local gate verification           | Run `cd frontend && npm run test -- --run && npm run type-check && npm run css:check` and `cdd-kit validate`. Confirm all 10 new cases pass, type-check stays green for all admin-dashboard tabs, and css:check passes. | frontend-engineer |
| IP-6 | UI / a11y review                  | Confirm `N/A` placeholder copy, slowlog list legibility, DuckDB section placement, and that new sections use existing Tailwind tokens. Log notes in agent-log.                                                          | ui-ux-reviewer    |
| IP-7 | Contract diff + release readiness | Verify AC-8 (PR diff contains zero files under `contracts/`); confirm all gates from ci-gates.md "Merge Eligibility" are green; sign off in agent-log.                                                                 | contract-reviewer, qa-reviewer |

## Source Artifact Pointers

| source                                                          | relevant pointer                                                                                  | used for                                                          |
|-----------------------------------------------------------------|---------------------------------------------------------------------------------------------------|-------------------------------------------------------------------|
| change-classification.md                                        | `## Inferred Acceptance Criteria` AC-1 .. AC-8                                                    | acceptance scope                                                  |
| test-plan.md                                                    | Acceptance Criteria → Test Mapping table (10 rows); New Test Files Needed                         | exact Vitest case names and file path                             |
| test-plan.md                                                    | Notes — vitest `include: ['src/**/*.test.ts']` glob covers the new file                           | no `vitest.config.js` change required                             |
| ci-gates.md                                                     | Required Gates table (vitest, css:check, cdd-kit validate, contracts/ diff check, type-check)     | gate commands to run locally and in CI                            |
| ci-gates.md                                                     | Workflow Changes Applied — `css:check` step in `frontend-tests.yml`                               | confirmation gate is live in CI                                   |
| ci-gates.md                                                     | Merge Eligibility list                                                                            | exit criteria for the change                                      |
| contracts/api/api-contract.md                                   | line ~290–292 (`fix-admin-dashboard` additive bullet — Redis 4 fields + DuckDB 2 fields)          | source-of-truth shape and nullability for the 6 fields            |
| contracts/css/css-inventory.md                                  | v1.2.2 (already bumped by prior task)                                                             | record that CSS inventory update is DONE — do not re-edit         |
| context-manifest.md                                             | Approved Expansions — CER-1 (`frontend/src/admin-dashboard/`)                                     | read+write permission for the admin-dashboard tabs                |
| frontend/src/admin-shared/composables/useAdminData.ts:88-93     | current `usePerfDetail()` signature (returns `unknown`)                                           | location for IP-2 type addition                                   |
| frontend/src/admin-dashboard/tabs/CacheTab.vue:93-117            | existing Redis `SectionCard` and `SummaryCardGroup`                                               | insertion point for IP-3                                          |
| frontend/src/admin-dashboard/tabs/PerformanceTab.vue:163-183    | existing 連線池 `SectionCard`                                                                      | new DuckDB SectionCard inserted immediately after this block      |

## File-Level Plan

| path or glob                                                          | action          | notes                                                                                                                                                                                                                            |
|-----------------------------------------------------------------------|-----------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| frontend/src/admin-dashboard/tabs/__tests__/PerfDetail.test.ts        | create          | 10 Vitest cases per test-plan.md. Mount CacheTab and PerformanceTab via `@vue/test-utils`. Inject fixture payloads (full / all-nulls / empty-slowlog / mixed) by stubbing the composables module or `apiGet`. Must fail before IP-2 .. IP-4. |
| frontend/src/admin-shared/composables/useAdminData.ts                 | edit (additive) | Add `PerfDetailSlowlogEntry`, `PerfDetailRedis`, `PerfDetailDuckDB`, `PerfDetailData`. Change `usePerfDetail` return type to `DataFetcher<PerfDetailData>`. Do not modify any other composable.                                  |
| frontend/src/admin-dashboard/tabs/CacheTab.vue                        | edit (additive) | Append 3 `SummaryCard`s inside the existing Redis `SummaryCardGroup`. Add slowlog `<ul>` inside the same Redis `SectionCard` (below namespaces table). No reorder or removal of existing markup.                                |
| frontend/src/admin-dashboard/tabs/PerformanceTab.vue                  | edit (additive) | Add a new `SectionCard` titled "DuckDB" (with `v-if="perfDetail?.duckdb"`) immediately after the 連線池 `SectionCard`. Inline `formatBytes` helper in `<script setup>`. No changes to chart, refresh, or pool rendering.       |
| frontend/src/admin-dashboard/tabs/WorkerTab.vue                       | no change       | Verify only — confirm that the new `PerfDetailData` type does not break this file's accesses (`perfDetail.value?.redis?.namespaces`, etc.). If a type error surfaces, widen the new interface; do not narrow the consumer.       |
| frontend/src/admin-dashboard/style.css                                | no change       | Use only Tailwind utilities and existing shared-ui primitives. If a render rule cannot be expressed without new authored CSS, STOP and report `blocked`.                                                                          |
| frontend/vitest.config.js                                             | no change       | `include: ['src/**/*.test.ts']` already covers the new test path.                                                                                                                                                                |
| .github/workflows/frontend-tests.yml                                  | no change       | `css:check` step already added per ci-gates.md "Workflow Changes Applied".                                                                                                                                                       |
| contracts/**                                                          | forbidden       | AC-8 — no file under `contracts/` may be modified by this PR. `css-inventory.md` v1.2.2 update is already done.                                                                                                                  |
| src/mes_dashboard/**                                                  | forbidden       | No backend change; the 6 fields are already emitted by the merged backend change.                                                                                                                                                |

## Contract Updates

- API: none — `/admin/api/performance-detail` 6-field additive update is already
  recorded in `contracts/api/api-contract.md` line ~290–292 by the merged
  `fix-admin-dashboard` change. Read-only confirmation only.
- CSS/UI: **already done** — `contracts/css/css-inventory.md` was bumped v1.2.1 →
  v1.2.2 by contract-reviewer in a prior step. Do not re-edit. If new authored CSS
  becomes unavoidable during implementation, STOP and report `blocked` (would
  violate AC-8 as currently scoped).
- Env: none.
- Data shape: none (rendering only; nullability already contracted). The
  `PerfDetailData` TS interface lives inside frontend code and is not a contract
  artifact.
- Business logic: none.
- CI/CD: none — `frontend-tests.yml` `css:check` step already in place per
  ci-gates.md "Workflow Changes Applied".

## Test Execution Plan

| acceptance criterion | test file / command                                                                                                              | expected signal                                                                |
|----------------------|----------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------|
| AC-1                 | `frontend/src/admin-dashboard/tabs/__tests__/PerfDetail.test.ts::renders evicted_keys and expired_keys as integers`              | CacheTab DOM contains both integer values inside Redis SummaryCardGroup         |
| AC-2                 | `PerfDetail.test.ts::renders mem_fragmentation_ratio with at most 2 decimal places`                                              | CacheTab DOM contains `value.toFixed(2)` string                                 |
| AC-3a                | `PerfDetail.test.ts::renders each slowlog entry when array is non-empty`                                                         | CacheTab DOM contains one `<li>` per slowlog entry; command + duration_us shown |
| AC-3b                | `PerfDetail.test.ts::renders placeholder when slowlog is null`                                                                   | CacheTab DOM shows literal `N/A`, no list items                                 |
| AC-3c                | `PerfDetail.test.ts::renders placeholder when slowlog is empty array`                                                            | CacheTab DOM shows literal `N/A`, no list items                                 |
| AC-4                 | `PerfDetail.test.ts::renders temp_dir_bytes as human-readable size`                                                              | PerformanceTab DOM contains formatted size string (e.g. `123.4 MB`)             |
| AC-5a                | `PerfDetail.test.ts::renders memory_limit_state string value`                                                                    | PerformanceTab DOM contains the literal string                                  |
| AC-5b                | `PerfDetail.test.ts::renders placeholder when memory_limit_state is null`                                                        | PerformanceTab DOM shows literal `N/A`                                          |
| AC-6                 | `PerfDetail.test.ts::all new fields null: no error thrown and sibling sections still render`                                     | No thrown error, no `console.error`; existing pool/Redis siblings still in DOM  |
| AC-7                 | `PerfDetail.test.ts::pre-existing performance-detail fields still render with full payload`                                      | Existing pool/Redis/namespaces/route-cache assertions pass; no regression       |
| AC-8                 | CI PR diff check (manual reviewer) + `cdd-kit validate`                                                                          | Zero files under `contracts/` in PR diff; cdd-kit validate green                |

Gate commands (run locally before opening PR; identical commands run in CI per ci-gates.md):

- `cd frontend && npm run test -- --run`
- `cd frontend && npm run css:check`
- `cd frontend && npm run type-check` (informational, `continue-on-error: true` in CI)
- `cdd-kit validate`

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into
  this plan; follow the Source Artifact Pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and
  report `blocked` rather than guessing.
- Follow TDD strictly: IP-1 (tests) must land in a failing state before IP-2 /
  IP-3 / IP-4 implementation. Do not merge a passing implementation that was
  never preceded by a failing test commit.
- Keep implementation within the file-level plan; any read or write outside it
  requires a new Context Expansion Request (`cdd-kit context request`).
- All null/undefined placeholders MUST render the literal string `N/A` (matches
  test-plan AC-3b / AC-3c / AC-5b / AC-6 and the existing `redisMemoryLabel`
  fallback in CacheTab.vue:38).
- Type changes to `usePerfDetail` MUST remain additive: every field currently
  read by PerformanceTab / CacheTab / WorkerTab must continue to type-check. If
  a consumer would break, widen the new interface; do not narrow callers.
- Do NOT modify any existing key rendering in any admin-dashboard tab (AC-7).
  All work is purely additive markup inside the existing Redis section
  (CacheTab) and a new DuckDB section (PerformanceTab).
- Do NOT modify any file under `contracts/` (AC-8). `css-inventory.md` v1.2.2 is
  already applied.
- Do NOT rename the `frontend-unit-tests` job in
  `.github/workflows/frontend-tests.yml` (branch protection dependency).
- Do NOT touch `frontend/src/admin-pages/`, `frontend/src/admin-user-usage-kpi/`,
  or any non-admin-dashboard SPA. The performance-detail consumer is exclusively
  admin-dashboard.

## Known Risks

- **Type widening surprises**: switching `usePerfDetail(): DataFetcher<unknown>`
  → `DataFetcher<PerfDetailData>` may surface latent unsafe property accesses in
  PerformanceTab / CacheTab / WorkerTab currently masked by `unknown` (e.g.
  `perfDetail.value?.redis?.namespaces`, `perfDetail.value?.db_pool?.status`,
  `perfDetail.value?.process_caches[name]`, `perfDetail.value?.route_cache?.mode`).
  Mitigation: ensure `PerfDetailData` is a superset that marks every existing
  field optional and untyped sub-fields as `unknown` or `Record<string, unknown>`
  where appropriate; run `npm run type-check` after IP-2 and before IP-3.
- **Test mocking strategy ambiguity**: `useAdminData` composables call `apiGet`
  directly. Two valid approaches:
  (a) `vi.mock('../../admin-shared/composables/useAdminData', ...)` to replace
      `usePerfDetail` with a stub that hands back `{ data: ref(fixture), ... }`;
  (b) `vi.mock('../../core/api', ...)` to stub `apiGet` and exercise the real
      composable.
  Frontend-engineer picks one and applies it consistently across all 10 cases.
- **Slowlog rendering format**: test-plan.md only requires that each entry's
  `command` and `duration_us` appear in the DOM. The exact UI treatment (`<ul>`
  with `<li>`, units suffix `μs`, ordering by `id`) is a UI-copy choice deferred
  to ui-ux-reviewer; pick the simplest list and let the reviewer escalate.
- **DuckDB null branch coverage**: when `perfDetail?.duckdb === null` (backend
  reports DuckDB telemetry unavailable), the SectionCard must be skipped
  entirely rather than rendered with two `N/A` placeholders, to match the
  existing Redis section's `v-if="perfDetail?.redis"` convention. The AC-6 test
  case must cover both "all 6 fields null inside non-null parents" AND "duckdb
  parent itself null" to lock this behavior.
- **CSS bleed risk**: any new authored selector in
  `frontend/src/admin-dashboard/style.css` would require a `css-inventory.md`
  re-bump, which AC-8 forbids in this PR. Stick to Tailwind utility classes and
  existing shared-ui primitives (`SectionCard`, `SummaryCard`,
  `SummaryCardGroup`). If unavoidable, STOP and report `blocked`.
- **slowlog payload variability**: backend returns up to top-5 entries. Tests
  must cover both a 5-entry fixture and a short-list fixture (e.g. 2 entries);
  rendering must not assume a fixed length.
