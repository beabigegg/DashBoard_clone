## Context

The mid-section-defect backward tracing page renders 5 Pareto charts. Three have bugs and a new chart is requested:

1. **依上游機台歸因** — inline MultiSelect filters for workcenter_group and machine type are conditionally rendered (`v-if="options.length > 1"`). The `upstreamStationOptions` and `upstreamSpecOptions` computed properties derive from `analysisData.attribution`, which is the raw machine attribution list. If the attribution data is empty or has only one group, filters disappear. Root cause: the attribution data is only populated when `eventsAggregation` returns — need to verify the field is correctly passed through the staged trace pipeline.

2. **依源頭批次歸因** — keyed by `ROOT_CONTAINER_NAME` from `_attribute_wafer_roots()`. The root name comes from `ANCESTOR_NAME` in the lineage query; when that field is NULL the fallback is `ancestor_id` (an opaque container ID). The user expects lot ID or work order. Fix: enrich the root attribution records with `CONTAINERNAME` (lot name) from detection_data when available, and prefer displaying lot name over raw ancestor IDs.

3. **依原物料歸因** — no inline filter exists. Need to add a material-part-name filter using the same pattern as the upstream machine chart (useFilterOrchestrator + inline MultiSelect).

4. **依Workflow歸因** (new) — `WORKFLOW` is already stored per attribution record. Need a new `by_workflow` chart dimension in the backend and a new ParetoChart in the frontend grid.

## Goals / Non-Goals

**Goals:**
- Restore upstream machine chart inline filters (workcenter_group + machine type)
- Fix source batch chart to display lot name / work order instead of raw container ID
- Add material type inline filter on raw material Pareto chart
- Add new "依Workflow歸因" Pareto chart for backward tracing

**Non-Goals:**
- Changing the forward tracing chart layout
- Modifying the trace pipeline stages or spool architecture
- Adding filters to loss reason or detection machine charts

## Decisions

### D1: Workflow chart — reuse `_build_chart_data` with `WORKFLOW` dimension on attribution records

The `WORKFLOW` field is already collected per attribution record (joined from detection_data in `_attribute_defects`). Adding `'by_workflow': 'WORKFLOW'` to `DIMENSION_MAP` lets `_build_all_charts` generate the chart data automatically with zero new aggregation logic.

**Alternative considered:** Build a separate `_attribute_workflows()` function like materials/wafer_root. Rejected because WORKFLOW is already a flat field on the machine-attribution records — no separate attribution source needed.

### D2: Source batch display — enrich `_attribute_wafer_roots` with detection lot's CONTAINERNAME

The `roots` mapping uses `ANCESTOR_NAME` which may be NULL (fallback = ancestor_id). To show meaningful lot names, enrich the `ROOT_CONTAINER_NAME` display by:
- In `_build_lineage_maps`: ensure `ANCESTOR_NAME` is always populated (it currently is for DuckDB runtime).
- In `_attribute_wafer_roots`: when root_name falls back to the lot's own containername, that's already correct. The issue is likely that some ancestors have no `ANCESTOR_NAME` in the lineage query, causing `ancestor_id` (UUID-like) to appear. Fix: propagate `CONTAINERNAME` from the lineage data more reliably.

**Alternative considered:** Join work order info into the root display. Rejected for now — lot name (CONTAINERNAME) is the standard identifier users recognise; adding work order is a future enhancement.

### D3: Material type filter — same pattern as upstream machine chart

Use `useFilterOrchestrator` with a `materialType` field. Derive options from `materials_attribution[].MATERIAL_PART_NAME`. Apply filter client-side on `analysisData.materials_attribution` then rebuild the chart via `_build_chart_data` equivalent in JS (same as `buildMachineChartFromAttribution` pattern).

### D4: Upstream machine filter fix — verify `analysisData.attribution` population

The `attribution` raw list must be passed through from the trace pipeline's events stage aggregation. If the staged trace response bundles it under a different key or omits it, the computed properties return empty arrays. Verify the data flow from `eventsAggregation` → `analysisData.attribution` and fix any missing assignment.

### D5: Chart grid layout — 3 rows for backward

Current backward layout: 2 rows (2+2) + 1 detection machine row = 5 charts.
New layout with workflow chart: rearrange to 3 rows:
- Row 1: 依上游機台歸因 | 依原物料歸因
- Row 2: 依源頭批次歸因 | 依Workflow歸因
- Row 3: 依不良原因 | 依偵測機台

## Risks / Trade-offs

- **[Risk] Upstream filters still empty after fix** → If the trace pipeline legitimately returns single-group data, filters won't show (by design). Document this as expected behaviour when data has only one workcenter_group.
- **[Risk] Workflow field has comma-separated values** → `_build_chart_data` already handles comma splitting (`if ',' in key`), so multi-workflow attribution records are handled correctly.
- **[Risk] Material filter adds client-side recomputation** → Same pattern already proven for upstream machine filter; performance impact is negligible for Top-N chart data.
