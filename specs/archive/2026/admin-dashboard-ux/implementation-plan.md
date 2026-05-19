---
change-id: admin-dashboard-ux
schema-version: 0.1.0
last-changed: 2026-05-19
---

# Implementation Plan: admin-dashboard-ux

## Objective

Deliver seven additive UX improvements to the admin-dashboard feature app: section reorder in `OverviewTab.vue` and `WorkerTab.vue`, threshold-driven accent colors on selected `SummaryCard` instances (CacheTab + PerformanceTab), human-readable Redis slowlog duration formatting, a shared "最後更新: HH:MM:SS" label rendered by every admin tab after each `refresh()`, and a clarified `TrendChart` empty-state copy. All changes are scoped to `frontend/src/admin-dashboard/`, `frontend/src/admin-shared/`, and a single additive prop extension to `frontend/src/shared-ui/components/SummaryCard.vue`. No backend, no contracts, no workflows, no new npm packages.

## Execution Scope

### In Scope
- Reorder DOM blocks in `OverviewTab.vue` (Active Alerts first) and `WorkerTab.vue` (TrendCharts after Worker 控制).
- Add optional `warningThreshold?: number`, `dangerThreshold?: number`, and `thresholdValue?: number` props to `frontend/src/shared-ui/components/SummaryCard.vue`. Replace the existing `accentColor` computed with threshold-aware logic that falls back to `props.accent` when both thresholds are absent or the comparison value is non-numeric.
- Wire threshold props in `CacheTab.vue` (mem_fragmentation_ratio, evicted_keys) and `PerformanceTab.vue` (DuckDB temp_dir_bytes via `thresholdValue`).
- Create `frontend/src/admin-shared/utils/formatDuration.ts` (pure function `formatDuration(us: number): string`) and use it in `CacheTab.vue` slowlog rendering.
- Create `frontend/src/admin-shared/composables/useLastUpdated.ts` exposing `{ lastUpdatedLabel: Ref<string>, markUpdated: () => void }`. Wire into all 6 admin-dashboard tabs.
- Change the empty-state of `frontend/src/admin-shared/components/TrendChart.vue` from a single `<div>` to a container with two separately-addressable child nodes: existing first line plus new second line `（每 30 秒自動收集一次）`.
- Author all Vitest specs listed in `test-plan.md` §Test File Inventory.

### Out of Scope
- Any backend file (Flask routes/services/workers/SQL).
- Any `.github/workflows/` change.
- Adding or removing npm packages.
- Renaming or relocating existing files. `SummaryCard.vue` stays under `shared-ui/components/`; `TrendChart.vue` stays under `admin-shared/components/`.
- Creating a separate `admin-shared/components/SummaryCard.vue` or `ThresholdCard.vue` wrapper (see Design Decision below).
- Changing any feature app outside admin-dashboard.
- CSS authoring outside the already-registered `admin-pages/style.css` scope (no new CSS files; `data-accent="warning|danger"` styling already exists in `SummaryCard.vue:206-217`).
- E2E / Playwright tests; `page_status.json`, `asset_readiness_manifest.json`, `route_scope_matrix.json` updates (no page added or removed).

## SummaryCard Design Decision (binding)

**Chosen: Approach A — extend `frontend/src/shared-ui/components/SummaryCard.vue` with additive optional threshold props. Rejected Approach B (new `admin-shared/ThresholdCard.vue` wrapper).**

Why A:
- All admin-dashboard tabs already import `../../shared-ui/components/SummaryCard.vue` (verified in OverviewTab, WorkerTab, CacheTab, PerformanceTab, UsageTab). A wrapper would force every threshold call-site to swap imports and would duplicate prop forwarding for zero behavior benefit.
- Props default to `undefined`. Every other feature app that imports the same SummaryCard remains a no-op — the established additive-prop pattern documented in `CLAUDE.md` "Shared UI Component Notes" (MultiSelect precedent).
- The test path in `test-plan.md` (`frontend/src/admin-shared/components/__tests__/SummaryCard.test.ts`) is the logical home for threshold unit tests; the tests `mount()` the actual component imported from `frontend/src/shared-ui/components/SummaryCard.vue`. `frontend/vitest.config.js` `include: ['src/**/*.test.ts']` already matches this path — no config change.

Why not B: would create a second component for tabs to import, duplicate forwarding, and increase review surface with no functional benefit.

Threshold accent logic inside SummaryCard `accentColor` computed:

```
const cmp = props.thresholdValue ?? props.value
const n = Number(cmp)
if (!Number.isFinite(n)) return props.accent
if (props.dangerThreshold != null && n >= props.dangerThreshold) return 'danger'
if (props.warningThreshold != null && n >= props.warningThreshold) return 'warning'
return props.accent
```

- Danger takes precedence over warning (AC-3).
- Both thresholds absent → returns `props.accent` (backward compatible).
- Non-numeric input → returns `props.accent`.
- Display value (`formattedValue` computed) is unchanged. Only `data-accent` switches.

`thresholdValue` is required for the PerformanceTab DuckDB card because its current `:value` is `formatBytes(...)` (a string like `"512.0 MB"`), which would coerce to `NaN`. The card binds `:value="formatBytes(perfDetail.duckdb.temp_dir_bytes)"` for display and `:thresholdValue="perfDetail.duckdb.temp_dir_bytes"` for comparison.

For CacheTab cards (`mem_fragmentation_ratio`, `evicted_keys`), `:value` is already numeric-coercible, so `thresholdValue` is not needed at those sites.

`evicted_keys` "warn when >0" with integer values is expressed as `warningThreshold=1` (the `>=` comparator then fires on the first evicted key without firing at 0). Add an inline `<!-- threshold=1 because counter is integer; >=1 == >0 -->` comment at the binding site.

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | `frontend/src/shared-ui/components/SummaryCard.vue` | Add `warningThreshold?: number`, `dangerThreshold?: number`, `thresholdValue?: number` to Props; rewrite `accentColor` computed per Design Decision logic. No CSS change. No template change. | frontend-engineer |
| IP-2 | `frontend/src/admin-dashboard/tabs/OverviewTab.vue` | Move the trailing `<SectionCard>` Active Alerts block to be the first SectionCard, after the initial `<section v-if="isInitialLoading">` and `<ErrorBanner>` but before "系統健康總覽". | frontend-engineer |
| IP-3 | `frontend/src/admin-dashboard/tabs/WorkerTab.vue` | Move both leading `<TrendChart>` blocks (Process/Server RSS + System Memory at lines 181–196) plus the mid-template TrendCharts (Async Worker + Queue Depth at lines 347–359) into one contiguous group placed AFTER the Worker 控制 `<SectionCard>` (currently ends at line 388). | frontend-engineer |
| IP-4 | `frontend/src/admin-dashboard/tabs/CacheTab.vue` | (a) Wire `:warningThreshold="1.5" :dangerThreshold="2.0"` on the `碎片率` SummaryCard (static accent stays `info`). (b) Wire `:warningThreshold="1"` on the `逐出鍵數` SummaryCard (static accent stays `danger`). (c) Import `formatDuration` and replace `{{ entry.duration_us }}μs` with `{{ formatDuration(entry.duration_us) }}` in slowlog list. | frontend-engineer |
| IP-5 | `frontend/src/admin-dashboard/tabs/PerformanceTab.vue` | On the DuckDB `Temp 目錄大小` SummaryCard add `:thresholdValue="perfDetail.duckdb.temp_dir_bytes"` and `:warningThreshold="524288000"`. Display binding `:value="formatBytes(...)"` unchanged. Static accent stays `info`. | frontend-engineer |
| IP-6 | `frontend/src/admin-shared/utils/formatDuration.ts` (new) | Pure exported function: returns `${(us/1_000_000).toFixed(1)}s` when `us >= 1_000_000`; `${(us/1_000).toFixed(1)}ms` when `us >= 1_000`; otherwise `${Math.round(us)}μs`. Non-numeric / null input returns `'-'`. Boundary at exactly 1000 → `1.0ms`; at 1_000_000 → `1.0s`. | frontend-engineer |
| IP-7 | `frontend/src/admin-shared/composables/useLastUpdated.ts` (new) | Exports `useLastUpdated(): { lastUpdatedLabel: Ref<string>, markUpdated: () => void }`. Initial label = `''`. `markUpdated()` formats `new Date()` local time as zero-padded `HH:MM:SS` and assigns `最後更新: HH:MM:SS`. | frontend-engineer |
| IP-8 | All 6 tab SFCs: `OverviewTab.vue`, `WorkerTab.vue`, `CacheTab.vue`, `PerformanceTab.vue`, `UsageTab.vue`, `LogsTab.vue` | Import `useLastUpdated`; instantiate `const { lastUpdatedLabel, markUpdated } = useLastUpdated();`; call `markUpdated()` at the end of `refresh()` after the `await Promise.all(...)` resolves successfully; render `<div class="admin-tab__last-updated">{{ lastUpdatedLabel }}</div>` in a consistent position (recommended: directly under the `<ErrorBanner>` line at the top of each tab template, so the label is visible from initial mount even if empty). | frontend-engineer |
| IP-9 | `frontend/src/admin-shared/components/TrendChart.vue` | Replace single `<div class="trend-chart-empty">趨勢資料不足（需至少 2 筆快照）</div>` with a wrapper containing two separately addressable child nodes (e.g., `<div class="trend-chart-empty"><div class="trend-chart-empty__primary">趨勢資料不足（需至少 2 筆快照）</div><div class="trend-chart-empty__hint">（每 30 秒自動收集一次）</div></div>`). Both lines must be queryable as distinct DOM nodes for `empty_state_second_line_is_separate_dom_node`. No new external CSS file; inline existing class or reuse. | frontend-engineer |
| IP-10 | Vitest specs (see File-Level Plan + Test Execution Plan) | Author all 5 new spec files per `test-plan.md` §Test File Inventory. Each requires `// @vitest-environment jsdom` pragma. | test-strategist (design) + frontend-engineer (author) |

## Source Artifact Pointers

| source | relevant pointer | used for |
|---|---|---|
| change-classification.md | Inferred Acceptance Criteria AC-1…AC-8 | scope, owner mapping, acceptance |
| change-classification.md | Optional Artifacts → `visual-review-report.md = yes` | ui-ux-reviewer must capture all 6 tabs |
| test-plan.md | §Test File Inventory (5 new spec files + existing PerfDetail) | tests to author |
| test-plan.md | §Notes — jsdom pragma; mock Date; useLastUpdated unit test | implementation constraints for test files |
| ci-gates.md | Required Gates table | verification commands |
| ci-gates.md | §Rollback Policy | git revert + `npm run build`; no parquet cleanup |
| context-manifest.md | §Allowed Paths | read boundary |

No `design.md` exists for this change (classification: Architecture Review Required = no; design.md = no). The binding design constraint is the SummaryCard Design Decision section above.

## File-Level Plan

| path or glob | action | notes |
|---|---|---|
| `frontend/src/shared-ui/components/SummaryCard.vue` | modify | Extend Props interface with 3 optional fields; rewrite `accentColor` computed. No CSS / template changes. |
| `frontend/src/admin-shared/components/TrendChart.vue` | modify | Empty-state container with two separately addressable child nodes carrying the existing copy + new second line `（每 30 秒自動收集一次）`. |
| `frontend/src/admin-shared/utils/formatDuration.ts` | create | Pure function per IP-6. |
| `frontend/src/admin-shared/composables/useLastUpdated.ts` | create | Composable per IP-7. |
| `frontend/src/admin-dashboard/tabs/OverviewTab.vue` | modify | Reorder per IP-2; useLastUpdated wiring per IP-8. |
| `frontend/src/admin-dashboard/tabs/WorkerTab.vue` | modify | Reorder per IP-3; useLastUpdated wiring per IP-8. |
| `frontend/src/admin-dashboard/tabs/CacheTab.vue` | modify | Thresholds + formatDuration per IP-4; useLastUpdated per IP-8. |
| `frontend/src/admin-dashboard/tabs/PerformanceTab.vue` | modify | DuckDB threshold per IP-5; useLastUpdated per IP-8. |
| `frontend/src/admin-dashboard/tabs/UsageTab.vue` | modify | useLastUpdated wiring only. |
| `frontend/src/admin-dashboard/tabs/LogsTab.vue` | modify | useLastUpdated wiring only. |
| `frontend/src/admin-shared/components/__tests__/SummaryCard.test.ts` | create | 9 cases per test-plan.md (AC-3). `mount()` the component from `shared-ui/components/SummaryCard.vue`. Include jsdom pragma. |
| `frontend/src/admin-shared/components/__tests__/TrendChart.test.ts` | create | 5 cases per test-plan.md (AC-7). jsdom pragma. |
| `frontend/src/admin-shared/composables/__tests__/useLastUpdated.test.ts` | create (optional per test-plan §Notes — author it) | Mock `Date`; verify label format and update sequence. |
| `frontend/src/admin-shared/utils/__tests__/formatDuration.test.ts` | create | Boundary tests at 999, 1000, 999_999, 1_000_000, non-numeric (covers AC-5 pure-function side). |
| `frontend/src/admin-dashboard/tabs/__tests__/OverviewTab.test.ts` | create | 5 cases (AC-1, AC-6). Stub `useHealthSummary` / `usePerfHistory`. jsdom pragma. |
| `frontend/src/admin-dashboard/tabs/__tests__/WorkerTab.test.ts` | create | 4 cases (AC-2, AC-6). Fixture must set `worker_memory_guard.enabled = true`. jsdom pragma. |
| `frontend/src/admin-dashboard/tabs/__tests__/CacheTab.test.ts` | create | 7 + 1 cases (AC-4, AC-5 DOM-level, AC-6). jsdom pragma. |
| `frontend/src/admin-dashboard/tabs/__tests__/PerfDetail.test.ts` | unchanged | Existing 8 tests must continue to pass (AC-8). |

## Contract Updates

- API: none.
- CSS/UI: none. Threshold logic reuses existing `[data-accent="warning"]` / `[data-accent="danger"]` rules in `SummaryCard.vue:206-217`. `admin-pages/style.css` registration at `contracts/css/css-inventory.md` 1.2.2 unchanged. No new authored CSS file.
- Env: none.
- Data shape: none (display-only).
- Business logic: none.
- CI/CD: none. `.github/workflows/frontend-tests.yml` already runs vitest + css:check + type-check on path filter `frontend/src/**`. `ci-gates.md` confirms no workflow modification required.

## Test Execution Plan

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 | `frontend/src/admin-dashboard/tabs/__tests__/OverviewTab.test.ts` (`active_alerts_section_is_first_section_card_in_dom`, `active_alerts_renders_before_status_grid`, `active_alerts_renders_before_trend_charts`) | `wrapper.findAllComponents(SectionCard)`: index 0 is Active Alerts |
| AC-2 | `frontend/src/admin-dashboard/tabs/__tests__/WorkerTab.test.ts` (`all_trend_charts_render_after_memory_guard_section`, `…after_async_workers_section`, `…after_worker_control_section`) | All TrendChart DOM positions > each SectionCard DOM position |
| AC-3 | `frontend/src/admin-shared/components/__tests__/SummaryCard.test.ts` (9 cases per test-plan) | `wrapper.attributes('data-accent')` matches expected per threshold rule; backward-compat case asserts unchanged behavior |
| AC-4 | `frontend/src/admin-dashboard/tabs/__tests__/CacheTab.test.ts` threshold section (7 cases) | Mounted CacheTab + PerformanceTab with fixtured values; assert `data-accent` on targeted SummaryCard nodes |
| AC-5 | `frontend/src/admin-shared/utils/__tests__/formatDuration.test.ts` (pure boundaries 999/1000/999999/1000000) + `CacheTab.test.ts` slowlog rendering (5 cases) | μs / ms / s suffix per boundary |
| AC-6 | OverviewTab / WorkerTab / CacheTab test files: `last_updated_label_updates_to_new_time_after_refresh` | After `await wrapper.vm.refresh()`, rendered text matches `最後更新: HH:MM:SS` for the mocked Date |
| AC-7 | `frontend/src/admin-shared/components/__tests__/TrendChart.test.ts` (5 cases) | Both empty-state lines present as separate DOM nodes when `snapshots.length < 2`; canvas hidden in empty state |
| AC-8 | `frontend/src/admin-dashboard/tabs/__tests__/PerfDetail.test.ts` (8 existing — no modification) | All pass unchanged |
| gate | `cd frontend && npm test` | Full vitest suite green (Tier 1 PR gate) |
| gate | `cd frontend && npm run css:check` | CSS governance pass (no new CSS) (Tier 1 PR gate) |
| gate | `cd frontend && npm run type-check` | informational; new optional props typed; no new `any` |
| gate | `cdd-kit gate admin-dashboard-ux --strict` | section-6 tasks resolved before commit |

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.
- Threshold props on `SummaryCard.vue` are strictly optional with `undefined` default. Any change that breaks existing consumers (the 9+ feature apps that import this component) is a regression and blocks merge. The `no_thresholds_uses_static_accent` and `non_numeric_value_with_thresholds_falls_back_to_static_accent` unit cases are the primary guards.
- Do not modify CSS files. The `data-accent="warning"` / `data-accent="danger"` styles already exist in `SummaryCard.vue` `<style scoped>` (lines 206–217); no new CSS is authored by this change.
- Do not rename or move `SummaryCard.vue`, `TrendChart.vue`, or any tab SFC.
- Do not extend threshold-prop usage to other feature apps in this change; threshold wiring outside admin-dashboard is out of scope.
- Every new `*.test.ts` requires `// @vitest-environment jsdom` because `frontend/vitest.config.js` defaults to `node`.
- AC-6 tests must mock `Date` (e.g., `vi.useFakeTimers(); vi.setSystemTime(new Date(...))`) before mount, or the assertion is non-deterministic.
- WorkerTab AC-2 fixture must set `worker_memory_guard.enabled = true` so the `v-if` SectionCard renders; otherwise the order assertion is vacuous.
- TrendChart empty-state second line uses full-width parentheses `（…）`. Preserve glyph fidelity. CLAUDE.md i18n rule does not apply (admin-dashboard is Chinese-only per change-classification A5).

## Known Risks

- **Cross-feature regression on SummaryCard**: 9+ feature apps import `shared-ui/components/SummaryCard.vue`. Backward compatibility depends entirely on the new props defaulting to `undefined` and `accentColor` returning `props.accent` when thresholds are absent. Mitigation: `SummaryCard.test.ts` `no_thresholds_uses_static_accent` case + full vitest suite.
- **PerformanceTab DuckDB threshold display vs. comparison mismatch**: the card displays `formatBytes(...)` (string). Without the `thresholdValue` prop, `Number("512.0 MB") = NaN` and the threshold never fires silently. Implementation must use `:thresholdValue="perfDetail.duckdb.temp_dir_bytes"`.
- **Last-updated label test determinism**: AC-6 tests must mock `Date` before `mount()`. Skipping this produces flaky CI.
- **Vitest environment pragma**: forgetting `// @vitest-environment jsdom` on any new spec produces `mount()` failures in the node default environment.
- **Visual review coverage (visual-review-report.md required)**: ui-ux-reviewer must capture all 6 tabs showing new section order, accent colors on the 3 wired cards, slowlog formatted durations, last-updated label, TrendChart empty-state second line. Missing captures blocks merge per ci-gates.md §Merge Eligibility.
- **Pre-commit gate**: `cdd-kit gate admin-dashboard-ux --strict` requires all section-6 tasks to be marked `done` or `skipped`. Per CLAUDE.md guidance, 6.2/6.3 may be marked done when local Tier 1 gates pass; 6.4 is `skipped` (no nightly/weekly/manual gates apply).
