# Visual Review Report — msd-forward-cause-effect

**Decision: approved with notes** (no blocking CSS-contract violations; 2 non-blocking advisories).

Reviewer: visual-reviewer (static source analysis — no screenshot tooling/baseline configured in repo; net-new surface, no regression diff required).

## Affected Screens
`frontend/src/mid-section-defect/` forward cause-effect UI: `App.vue` (forward branch: hero, selection banner), `components/ForwardFlowChart.vue` (Sankey), `components/ForwardHeatmap.vue` (heatmap), `components/KpiCards.vue` (7-card forward grid + 放大倍率), `components/DetailTable.vue` (前段不良原因 column), `style.css` (`.forward-hero-*` / `.forward-selection-banner`, lines 655–745).

## Evidence
- `npm run build` — exit 0 (13.32s), no errors.
- `npm run type-check` (vue-tsc) — exit 0.
- `npm run css:check` — **0 errors**, 307 warnings (all pre-existing codebase-wide; 0 new from this change).
- Screenshots: none (no Percy/Chromatic/Playwright baseline; net-new surface).

## State Coverage (all PASS)
default / empty (暫無資料) / selection-active (non-selected nodes dimmed, links opacity) / selection-cleared / toggle-sankey / toggle-heatmap / amplification null→"—" (neutral) / >1 (danger) / =1 (warning) / 0→"×0.0" (neutral) / detail forward columns / banner visible+hidden.

## CSS Contract Findings (all PASS)
- Rule 4.2/4.3 (theme scope): all new rules scoped under `.theme-mid-section-defect`; css:check 0 unscoped feature-CSS rules.
- Rule 4.4 (Teleport tooltip): N/A — neither chart uses `<Teleport>`/`appendToBody`; ECharts tooltip renders in chart canvas.
- Rule 4.5 (`:is()` groups): `.theme-mid-section-defect` already present in resource-shared/styles.css groups (predates this change).
- Rule 6.2/6.3 (ECharts colors as constants): `ForwardFlowChart` defines named SANKEY_* constants; heatmap uses inline visualMap colors (chart-context exception, advisory to extract).
- Rule 3.3 (no inline static style): PASS. Rule 7.2 (css-inventory): updated, no new CSS file.
- SummaryCard accent values (info/danger/brand/neutral/warning/success) all valid.

## Advisories (non-blocking, designer acknowledgement)
- **A — tablet KPI orphan**: 7-card forward grid at ≤1000px → 3+3+1 (last card full-width, asymmetric). Acceptable under shared `SummaryCardGroup` contract; optionally adjust MSD breakpoint.
- **B — redundant class**: `charts-row-full` on the forward-hero `<div>` is a no-op (block element, not grid child); visual result correct, class misleading — cleanup optional.
- Minor: detail `DETECTION_LOSS_REASON` column 130px may truncate long zh strings (contained in scroll wrapper, nowrap); could widen to 150–160px.

## Verdict
No blocking issues. Build/type-check/css:check clean. Advisories tracked for optional follow-up. The UX/a11y blocking items (heatmap clear-affordance, aria-pressed) are owned by the ui-ux review, addressed in the same PR.
