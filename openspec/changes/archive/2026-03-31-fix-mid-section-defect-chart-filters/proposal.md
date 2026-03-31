## Why

The mid-section-defect backward tracing page has three UI/display bugs and one missing feature: (1) the "依上游機台歸因" chart lost its dedicated workcenter_group and machine type filters, (2) the "依源頭批次歸因" chart displays container IDs instead of work orders or lot IDs, (3) the "依原物料歸因" chart lacks a material type filter, and (4) there is no "依Workflow歸因" Pareto chart — users need to see defect attribution broken down by workflow.

## What Changes

- **Bug #1 — Upstream machine chart filters disappeared**: The inline `MultiSelect` filters for workcenter_group and machine type are conditionally rendered with `v-if="options.length > 1"`. Investigate why the options are empty (likely `attribution` data no longer carries `WORKCENTER_GROUP` / `RESOURCEFAMILYNAME` fields, or the computed properties produce no results). Fix the root cause so filters appear when attribution data has multiple groups.
- **Bug #2 — Source batch chart shows container ID instead of work order / lot ID**: The `by_wafer_root` chart is keyed by `ROOT_CONTAINER_NAME` (a raw container ID). Change the display label to show the work order or lot ID where available, falling back to container name only when no lot/WO mapping exists.
- **Bug #3 — Add material type filter to raw material chart**: Add an inline filter (similar to the upstream machine chart's pattern) on the "依原物料歸因" Pareto chart so users can filter by material type (`MATERIALPARTNAME` category or a grouping field).
- **Feature #4 — Add "依Workflow歸因" Pareto chart**: Add a new backward-tracing Pareto chart that attributes defects by `WORKFLOW`. The `WORKFLOW` field is already present in `detection_data` and attribution records. Build the chart using the same `_build_chart_data` pattern as other dimensions, and render it in the backward chart grid.

## Capabilities

### New Capabilities
_None_

### Modified Capabilities
- `msd-multifactor-attribution`: Add material type filter requirement for the materials Pareto chart; fix display field for wafer root Pareto chart (lot/WO instead of container ID); ensure upstream machine chart filter options are populated from attribution data; add "依Workflow歸因" Pareto chart requirement.

## Impact

- **Frontend**: `frontend/src/mid-section-defect/App.vue` — fix upstream filter computed properties, add material type filter orchestrator, update by_wafer_root display binding, add new "依Workflow歸因" ParetoChart.
- **Backend**: `src/mes_dashboard/services/mid_section_defect_service.py` — may need to include lot/WO mapping in `by_wafer_root` chart data; expose material type grouping field in `by_material` attribution data; add `by_workflow` chart data using `WORKFLOW` field from detection_data (already available, just needs aggregation via `_build_chart_data`).
- **Spec**: `openspec/specs/msd-multifactor-attribution/spec.md` — update requirements for filter presence, display fields, and new workflow chart.
