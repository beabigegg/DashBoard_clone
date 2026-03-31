## 1. Bug #1 — Restore upstream machine chart filters

- [x] 1.1 Verify `analysisData.attribution` is correctly populated from `eventsAggregation` in App.vue (check that raw attribution list with `WORKCENTER_GROUP` and `RESOURCEFAMILYNAME` is assigned, not just chart data)
- [x] 1.2 Fix the data flow if attribution is missing — ensure the staged trace pipeline returns the raw attribution list and App.vue stores it at `analysisData.attribution`
- [x] 1.3 Verify `upstreamStationOptions` and `upstreamSpecOptions` computed properties return correct options when attribution data is present

## 2. Bug #2 — Fix source batch chart display (lot name instead of container ID)

- [x] 2.1 In `_build_lineage_maps` (msd_duckdb_runtime.py), ensure `ANCESTOR_NAME` is always used for root names and never falls back to raw `ancestor_id` when `ANCESTOR_NAME` is available
- [x] 2.2 In `_attribute_wafer_roots` (mid_section_defect_service.py), ensure the self-root fallback uses `containername` (lot name) from `detection_data`, not the container ID key
- [x] 2.3 Verify the `by_wafer_root` chart displays lot names (CONTAINERNAME) in the rendered ParetoChart

## 3. Bug #3 — Add material type filter to raw material chart

- [x] 3.1 Add `useFilterOrchestrator` for material chart with a `materialType` field in App.vue
- [x] 3.2 Add computed property `materialTypeOptions` deriving distinct `MATERIAL_PART_NAME` values from `analysisData.materials_attribution`
- [x] 3.3 Add computed property `filteredByMaterialData` that filters `materials_attribution` by selected material types and rebuilds chart data
- [x] 3.4 Store raw `materials_attribution` list in `analysisData` (same pattern as `attribution` for machine chart)
- [x] 3.5 Add inline MultiSelect filter in the「依原物料歸因」ParetoChart `#header-extra` slot

## 4. Feature #4 — Add "依Workflow歸因" Pareto chart

- [x] 4.1 Add `'by_workflow': 'WORKFLOW'` to `DIMENSION_MAP` in mid_section_defect_service.py
- [x] 4.2 Verify `_build_all_charts` produces `by_workflow` chart data correctly
- [x] 4.3 Add `<ParetoChart title="依Workflow歸因" :data="analysisData.charts?.by_workflow" />` in the backward chart grid in App.vue

## 5. Layout — Update backward chart grid to 6 charts

- [x] 5.1 Rearrange backward chart template to 3 rows: Row 1 (機台 | 原物料), Row 2 (源頭批次 | Workflow), Row 3 (不良原因 | 偵測機台)
- [x] 5.2 Update `skeletonChartCount` computed to return 6 for backward direction

## 6. Testing

- [x] 6.1 Verify upstream machine chart filters appear when attribution data has multiple workcenter groups
- [x] 6.2 Verify source batch chart shows lot names, not container IDs
- [x] 6.3 Verify material type filter narrows the material Pareto chart correctly
- [x] 6.4 Verify workflow Pareto chart renders with correct data
- [x] 6.5 Run existing tests: `pytest tests/test_mid_section_defect_service.py tests/test_mid_section_defect_engine.py -v`
