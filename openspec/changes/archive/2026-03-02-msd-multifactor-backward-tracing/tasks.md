## 1. Backend: Multi-factor attribution engine

- [x] 1.1 Add `_attribute_materials()` to `mid_section_defect_service.py` — symmetric to `_attribute_defects()`, keyed by `(MATERIALPARTNAME, MATERIALLOTNAME)`, handles NULL lot name gracefully
- [x] 1.2 Add `_attribute_wafer_roots()` to `mid_section_defect_service.py` — keyed by `root_container_name`, builds `root → detection_lots` mapping from lineage roots
- [x] 1.3 Update `DIMENSION_MAP` — remove `by_package`, `by_pj_type`, `by_workflow`; add `by_material`, `by_wafer_root`
- [x] 1.4 Update `_build_all_charts()` to call the new attribution functions for `by_material` and `by_wafer_root` dimensions
- [x] 1.5 Add `lot_count` field to each Pareto bar entry in `_build_chart_data()` (number of associated detection LOTs for that factor)

## 2. Backend: Lineage root extraction

- [x] 2.1 Add root identification logic to `lineage_engine.py` — traverse `child_to_parent` map to find the node with no further parent for each seed
- [x] 2.2 Include `roots` field (`{seed_cid: root_container_name}`) in lineage stage response
- [x] 2.3 Pass `roots` through `build_trace_aggregation_from_events()` into aggregation context

## 3. Backend: Staged trace materials domain

- [x] 3.1 In `trace_routes.py` events stage, add `materials` to the domain list for `mid_section_defect` profile backward mode
- [x] 3.2 Wire materials domain records through `_flatten_domain_records()` into aggregation input

## 4. Backend: Structured detail table

- [x] 4.1 Modify `_build_detail_table()` — change `UPSTREAM_MACHINES` from comma-separated string to list of `{"station": "...", "machine": "..."}` objects
- [x] 4.2 Add `UPSTREAM_MATERIALS` field to detail records — list of `{"part": "...", "lot": "..."}` objects (when materials data is available)
- [x] 4.3 Add `WAFER_ROOT` field to detail records — root ancestor `CONTAINERNAME` string
- [x] 4.4 Add `UPSTREAM_MACHINE_COUNT` field to detail records — count of unique upstream machines per LOT
- [x] 4.5 Update CSV export in `mid_section_defect_routes.py` — flatten structured `UPSTREAM_MACHINES` back to comma-separated `station/machine` format for CSV compatibility

## 5. Backend: Equipment recent jobs endpoint

- [x] 5.1 Add `GET /api/query-tool/equipment-recent-jobs/<equipment_id>` endpoint in `query_tool_routes.py` — query `DW_MES_JOB` for last 30 days, return top 5 most recent JOB records (JOBID, JOBSTATUS, JOBMODELNAME, CREATEDATE, COMPLETEDATE)
- [x] 5.2 Add SQL file `src/mes_dashboard/sql/query_tool/equipment_recent_jobs.sql` for the query

## 6. Backend: Reject history Pareto dimensions

- [x] 6.1 Add `dimension` parameter to `query_reason_pareto()` in `reject_history_service.py` — support `reason` (default), `package`, `type`, `workflow`, `workcenter`, `equipment` as groupby keys
- [x] 6.2 Update `reject_history_routes.py` to accept and pass `dimension` query parameter
- [x] 6.3 Ensure two-phase caching still works (groupby from cached DataFrame, no re-query)

## 7. Backend: Analysis summary data

- [x] 7.1 Add `total_ancestor_count` to lineage stage response — count of unique ancestor CIDs (excluding seed CIDs)
- [x] 7.2 Ensure backward aggregation response includes summary fields: total detection lots, total input qty, defective lot count, total reject qty, ancestor coverage count

## 8. Frontend: Multi-factor Pareto charts

- [x] 8.1 Update `App.vue` backward chart section — replace 6-chart layout with 5-chart layout (2-2-1): machine | material, wafer_root | loss_reason, detection_machine
- [x] 8.2 Add chart builder functions for materials and wafer root attribution data (same pattern as `buildMachineChartFromAttribution`)
- [x] 8.3 Update `useTraceProgress.js` — in backward mode, request `domains: ['upstream_history', 'materials']`
- [x] 8.4 Wire new chart data through session caching (save/load from sessionStorage)

## 9. Frontend: Pareto chart enhancements (ParetoChart.vue)

- [x] 9.1 Add sort toggle button (依不良數 / 依不良率) — per-chart state, re-sort data and recalculate cumulative %
- [x] 9.2 Add 80% cumulative markLine — horizontal dashed line at y=80 on percentage axis, muted color `#94a3b8`, label「80%」
- [x] 9.3 Add `lot_count` to tooltip formatter — show「關聯 LOT 數: N (xx%)」

## 10. Frontend: Analysis summary panel

- [x] 10.1 Create `AnalysisSummary.vue` component — collapsible panel with query context, data scope stats, and attribution methodology text
- [x] 10.2 Integrate into `App.vue` above KPI cards — pass query params and summary data as props
- [x] 10.3 Handle container mode variant (show input type and resolved count instead of date range)
- [x] 10.4 Persist collapsed/expanded state in sessionStorage

## 11. Frontend: Detail table suspect hit column

- [x] 11.1 Update `DetailTable.vue` — replace「上游機台」column with「嫌疑命中」column
- [x] 11.2 Implement suspect list derivation — extract machine names from current Pareto Top N (respecting inline station/spec filters)
- [x] 11.3 Render hit cell: show matching machine names with ratio (e.g., `WIRE-03, DIE-01 (2/5)`), star/highlight for full match,「-」for no hits
- [x] 11.4 Add「上游台數」column showing total unique upstream machine count per LOT
- [x] 11.5 Make suspect list reactive to Pareto inline filter changes

## 12. Frontend: Suspect machine context panel

- [x] 12.1 Create `SuspectContextPanel.vue` — popover component with attribution summary section and maintenance section
- [x] 12.2 Attribution summary content: equipment name, workcenter group, resource family, defect rate, defect count, input count, LOT count (all available from existing attribution data)
- [x] 12.3 Maintenance section: fetch recent JOB records from `/api/query-tool/equipment-recent-jobs/<equipment_id>`, show up to 5 records; loading state while fetching;「近 30 天無維修紀錄」when empty
- [x] 12.4 Integrate with ParetoChart.vue — emit click event on bar for「依上游機台歸因」chart only; position popover near clicked bar
- [x] 12.5 Close on outside click or re-click of same bar

## 13. Frontend: Reject history Pareto dimensions

- [x] 13.1 Add dimension selector dropdown to `ParetoSection.vue` in reject-history — options: 不良原因, PACKAGE, TYPE, WORKFLOW, 站點, 機台
- [x] 13.2 Update API call to pass `dimension` parameter
- [x] 13.3 Update `App.vue` in reject-history to wire dimension state

## 14. Tests

- [x] 14.1 Add unit tests for `_attribute_materials()` in `tests/test_mid_section_defect.py` — verify correct rate calculation, NULL lot name handling
- [x] 14.2 Add unit tests for `_attribute_wafer_roots()` — verify root mapping, self-root case
- [x] 14.3 Add unit tests for structured `_build_detail_table()` output — verify list format, CSV flatten
- [x] 14.4 Add tests for equipment-recent-jobs endpoint in `tests/test_query_tool_routes.py`
- [x] 14.5 Add tests for reject history dimension Pareto in `tests/test_reject_history_routes.py`
- [x] 14.6 Run full test suite and fix regressions
