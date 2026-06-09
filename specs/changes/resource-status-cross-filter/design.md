# Design — resource-status-cross-filter

## Architecture Summary

Generalize the existing client-side `matrixFilter[]` pattern in `resource-status/App.vue`
into a single reusable composable, `useCrossFilter.ts`, that holds all client-side
selection state for the page. Every chart (WorkcenterOuRings, OuHeatmap, MatrixSection,
MaintenanceAlerts, SummaryCardGroup) becomes a *contributor* that emits a typed
selection descriptor when an element is clicked; every chart and EquipmentGrid become
*consumers* that render against the AND-intersection of all active selections derived
from the same `allEquipment` flat array. No backend change: `/api/resource/status`
payload is unchanged and all filtering is in-memory. This is purely a frontend
state-management + UI-affordance change, bounded to `frontend/src/resource-status/`.

## Affected Components

| component | file path | nature of change |
|---|---|---|
| Cross-filter composable | `frontend/src/resource-status/composables/useCrossFilter.ts` | NEW — selection state, AND-intersection reducer, toggle/clear/exclude-self |
| Page root | `frontend/src/resource-status/App.vue` | Replace `matrixFilter`/`summaryStatusFilter` refs + `displayedEquipment` with composable; pass filtered subset to all 4 charts; wire click handlers |
| Ring chart | `frontend/src/resource-status/components/WorkcenterOuRings.vue` | Add `@click` on `<VChart>` → emit selection (group+status); add `:selection` prop for highlight |
| Heatmap | `frontend/src/resource-status/components/OuHeatmap.vue` | Native cell `@click` → emit selection (group+package); highlight active cell |
| Matrix | `frontend/src/resource-status/components/MatrixSection.vue` | Keep existing `cell-filter` emit; re-point handler to composable (no emit-shape change) |
| Alerts | `frontend/src/resource-status/components/MaintenanceAlerts.vue` | Add row `@click` → emit selection (resource); keep existing `show-job` emit |
| Equipment grid | `frontend/src/resource-status/components/EquipmentGrid.vue` | Consume intersection subset + clear-all (largely unchanged) |
| Styles | `frontend/src/resource-status/style.css` | Add `.theme-resource-status`-scoped selection-highlight / clear-button rules |

## Key Decisions

### D1 — Cross-filter intersection semantics
**AND-intersection across charts** (PowerBI behavior). Each contributor emits a partial
predicate over the shared `EquipmentItem` shape; the composable stores an ordered set of
active selections and an equipment row is shown iff it matches *every* active selection.
Dimension contribution by chart: Ring → `{WORKCENTER_GROUP, status}`; Heatmap →
`{WORKCENTER_GROUP, PACKAGEGROUPNAME}`; Matrix → `{WORKCENTER_GROUP, status, family?,
resource?}`; Alerts → `{RESOURCEID}`; SummaryCard → `{status}`. Selections are keyed by a
stable string (chart-source + dimension values) so re-click toggles the same entry.
*Rejected:* single-active-selection — simpler but cannot express "UDT ∧ QFP" drill-in,
which is the stated user goal; would also be a behavioral regression from today's
`matrixFilter[]` which already supports multiple stacked filters.

### D2 — matrixFilter / summaryStatusFilter unification
**Unify** both into `useCrossFilter`. `matrixFilter[]` is the exact pattern being
generalized, and `summaryStatusFilter` is a single-dimension special case of it; keeping
them parallel would create precedence ambiguity (e.g., does a ring click AND or replace a
matrix filter?) and duplicate the reducer. After unification, `displayedEquipment`,
`activeFilterText`, and the `EquipmentGrid v-if` gate all derive from the composable's
`activeSelections`/`filteredEquipment`. *Regression implication:* existing legacy
behavior (matrix cell toggle, summary-card toggle, clear-all, active-filter label text)
must be re-proven against the composable — `frontend/tests/legacy/resource-status.test.js`
must pass unchanged, and the new `useCrossFilter` unit tests must cover the matrix and
summary-card dimensions explicitly so the migration is not a silent behavior drop.

### D3 — Clear-selection UX
Support **re-click toggle AND a clear button**. Re-clicking an active element removes its
selection from the intersection (existing `applyMatrixFilter` toggle semantics, now in the
composable). A "清除全部" clear control is shown (reuse EquipmentGrid's existing
`clear-filter` affordance) whenever `activeSelections.length > 0`. **ESC**: when focus is
on a selected, clickable element, ESC clears *that element's* selection and returns focus
to the element via `nextTick(() => el.focus())`, per CLAUDE.md Accessibility Notes
(combobox/popup close-path focus-return rule). ESC with no focused selection is a no-op.

### D4 — ECharts click-binding approach
**Use vue-echarts `@click` on the `<VChart>` component.** WorkcenterOuRings already
renders via the `vue-echarts` `<VChart>` wrapper, which forwards native ECharts events as
Vue events carrying `params.name`/`params.data`. Binding `@click` in the template needs no
`onMounted`/manual `chart.on(...)` registration and no `onUnmounted` cleanup — the wrapper
disposes the instance on unmount, so there is no leak risk and it stays type-safe within
the SFC. *Rejected:* manual `echartsInstance.on('click')` and ECharts `select` mode — both
require imperative lifecycle wiring and cleanup that the wrapper already handles, and
`select` mode would couple visual state to ECharts internals instead of the composable
(the single source of truth per D2).

### D5 — Phase 2 dim effect
**Out of scope.** Visual dimming/opacity of non-selected elements is deferred to a
follow-up change. This change delivers selection + intersection filtering + a clear
highlight on the selected element only (AC-8). frontend-engineer must NOT implement
opacity/dim affordances on non-selected elements; if pulled in later it requires a
ui-ux-reviewer visual-review-report (per change-classification optional-artifacts note).

## Migration / Rollback Strategy

No backend, schema, or contract-shape change, so rollback is a straight revert of the
frontend commit; no data or persisted-state migration is involved (all selection state is
ephemeral, in-memory, per page session). The only "migration" is internal: state
previously held in two refs (`matrixFilter[]`, `summaryStatusFilter`) moves into
`useCrossFilter`. Because that state is never persisted or shared across pages/sessions,
there is nothing to migrate at runtime — a reverted build simply restores the old refs.
Regression safety rests on the unchanged legacy test file plus the new composable and
App-level intersection tests; if any legacy assertion cannot be satisfied by the unified
composable, prefer keeping the legacy emit/prop surface intact over loosening the test.

## Open Risks

- **Exclude-self correctness (AC-3):** each chart must still render *all* values for its
  own dimension while reflecting other charts' selections. The intersection reducer must
  exclude a chart's own contributed dimension when computing that chart's input set, or a
  ring click will hide the other rings. Pin with a "selecting A narrows B but not A" test
  (CLAUDE.md cross-filter discipline).
- **Heatmap package dimension has no existing filter precedent** (`PACKAGEGROUPNAME` was
  never a `matrixFilter` field); verify the predicate handles the `null`/`'—'` trim case
  consistently with OuHeatmap's `eq.PACKAGEGROUPNAME?.trim() || '—'` grouping.
- **Legacy test coupling:** `frontend/tests/legacy/resource-status.test.js` may assert on
  the internal `matrixFilter` ref name/shape; unification could require test-strategist to
  update assertions to the composable surface without weakening intent.
