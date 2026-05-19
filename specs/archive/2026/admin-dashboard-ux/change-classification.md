# Change Classification

## Change Types
- primary: ui-only-change, feature-enhancement
- secondary: refactor (additive prop API extension on SummaryCard)

## Risk Level
- low

## Impact Radius
- module-level (scoped to admin-dashboard feature app + admin-shared SummaryCard/TrendChart)

## Tier
- 3

## Architecture Review Required
- no
- reason: purely additive UI/UX changes within an existing feature module; no module-boundary, data-flow, or migration decisions

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | |
| proposal.md | no | |
| spec.md | no | |
| design.md | no | architecture review not required; SummaryCard prop addition is additive and trivial |
| qa-report.md | no | pass/fail logged in agent-log; no blocking findings expected |
| regression-report.md | no | layout reorders and additive props; regression captured in test-plan |
| visual-review-report.md | yes | UI layout reorder + new accent color logic + new last-updated label + new empty-state copy require durable visual evidence across 6 tabs |
| monkey-test-report.md | no | |
| stress-soak-report.md | no | |

## Required Contracts
- API: none
- CSS/UI: none (admin-pages/style.css already registered at css-inventory 1.2.2; no new authored CSS file; rules must remain scoped under existing theme class)
- Env: none
- Data shape: none
- Business logic: none
- CI/CD: none

## Required Tests
- unit: SummaryCard threshold logic (warn/danger boundary cases, missing thresholds, non-numeric values); slowlog duration formatter (μs/ms/s tier boundaries: 999, 1000, 999999, 1000000); last-updated timestamp formatter
- contract: none
- integration: tab-level Vitest covering refresh()→last-updated label update, OverviewTab section order, WorkerTab section order
- E2E: none (Tier 3 + UI-only reorder; visual review covers the user-facing assertion)
- visual: snapshot/manual capture of all 6 tabs showing new section order, threshold-driven accent colors on mem_fragmentation_ratio / evicted_keys / DuckDB temp_dir_bytes, slowlog formatted durations, last-updated label, TrendChart empty-state second line
- data-boundary: none
- resilience: none
- fuzz/monkey: none
- stress: none
- soak: none

## Required Agents
- implementation-planner
- frontend-engineer
- test-strategist
- ui-ux-reviewer
- contract-reviewer
- qa-reviewer

## Inferred Acceptance Criteria
- AC-1: OverviewTab.vue renders the "Active Alerts" SectionCard as the first child above the status grid and trend charts; DOM order is verified by a Vitest assertion.
- AC-2: WorkerTab.vue renders the 4 trend chart components (Process/Server RSS, System Memory, Async Worker, Queue Depth) AFTER the current-state SectionCards (memory guard, async workers, worker control); DOM order is verified by a Vitest assertion.
- AC-3: SummaryCard accepts optional `dangerThreshold` and `warningThreshold` numeric props; when both are absent the static `accent` prop continues to drive color (backward compatible); when a threshold is set, the rendered accent class switches to warning when `value >= warningThreshold` and danger when `value >= dangerThreshold`, with danger taking precedence over warning.
- AC-4: SummaryCard threshold props are wired for mem_fragmentation_ratio (warn ≥1.5, danger ≥2.0), evicted_keys (warn >0), and DuckDB temp_dir_bytes (warn ≥524288000 bytes).
- AC-5: CacheTab.vue Redis slowlog rows display `duration_us` formatted as: `Xs` when ≥1_000_000μs, `Xms` when ≥1_000μs and <1_000_000μs, otherwise `Xμs`; unit boundary values (999, 1000, 999_999, 1_000_000) are unit-tested.
- AC-6: Every admin-dashboard tab (Overview, Performance, Cache, Worker, Usage, Logs) renders a "最後更新: HH:MM:SS" label that updates to the current time after every successful refresh() call.
- AC-7: TrendChart.vue empty state (hasData === false) renders "趨勢資料不足（需至少 2 筆快照）" followed by a second line "（每 30 秒自動收集一次）".
- AC-8: All existing admin-dashboard Vitest specs continue to pass; no admin CSS rules introduced outside the existing scoped theme.

## Tasks Not Applicable
- not-applicable: 1.3

## Clarifications or Assumptions
- A1: SummaryCard.vue and TrendChart.vue live under frontend/src/admin-shared/components/ — manifest already allows both admin-shared and admin-dashboard directories.
- A2: "DuckDB temp_dir_bytes > 500MB" threshold = ≥524_288_000 bytes (the card receives raw bytes from backend).
- A3: "last-updated" label should be implemented as a shared composable in admin-shared/composables/ to avoid duplication across 6 tabs.
- A4: No page_status.json, asset_readiness_manifest.json, or route_scope_matrix.json updates needed — no page added/removed.
- A5: Admin-dashboard is Chinese-only; i18n sync rule (CLAUDE.md rule #5) does not apply.
