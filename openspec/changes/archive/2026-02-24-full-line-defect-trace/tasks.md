## 1. SQL Layer

- [x] 1.1 Create `station_detection.sql` — copy `tmtt_detection.sql`, replace hardcoded TMTT filter with `{{ STATION_FILTER }}` / `{{ STATION_FILTER_REJECTS }}` placeholders, rename `TMTT_EQUIPMENTID/NAME` → `DETECTION_EQUIPMENTID/NAME`
- [x] 1.2 Create `downstream_rejects.sql` — query `DW_MES_LOTREJECTHISTORY` for batched CONTAINERIDs with `WORKCENTER_GROUP` CASE WHEN, returning CONTAINERID, WORKCENTERNAME, WORKCENTER_GROUP, LOSSREASONNAME, EQUIPMENTNAME, REJECT_TOTAL_QTY, TXNDATE
- [x] 1.3 Modify `upstream_history.sql` — add `h.TRACKINQTY` (with COALESCE to 0) to `ranked_history` CTE and final SELECT

## 2. Backend Service — Station Parameterization

- [x] 2.1 Add `_build_station_filter(station_name, column_prefix)` to `mid_section_defect_service.py` — reads `WORKCENTER_GROUPS` patterns/exclude, builds OR-LIKE SQL with bind params
- [x] 2.2 Replace `_fetch_tmtt_data()` with `_fetch_station_detection_data(start_date, end_date, station)` — uses `station_detection.sql` + `_build_station_filter()`
- [x] 2.3 Update all public API signatures (`query_analysis`, `query_analysis_detail`, `export_csv`, `resolve_trace_seed_lots`, `build_trace_aggregation_from_events`) to accept `station` and `direction` params (default `'測試'`/`'backward'`)
- [x] 2.4 Add station+direction to cache keys
- [x] 2.5 Rename all internal `TMTT_` → `DETECTION_` references (variables, dict keys, DIMENSION_MAP entries)

## 3. Backend Service — Forward Pipeline

- [x] 3.1 Extract existing backward logic into `_run_backward_pipeline(start_date, end_date, station, loss_reasons)`
- [x] 3.2 Add `_fetch_downstream_rejects(tracked_cids)` — batch query using `downstream_rejects.sql`
- [x] 3.3 Implement `_attribute_forward_defects(detection_df, detection_cids, downstream_wip, downstream_rejects, station_order)` — per-station reject rate using TRACKINQTY denominator
- [x] 3.4 Implement `_run_forward_pipeline(start_date, end_date, station, loss_reasons)` — full 8-stage pipeline (detection → forward lineage → downstream WIP+rejects → attribution → KPI/charts/detail)
- [x] 3.5 Implement `_build_forward_kpi()`, `_build_forward_charts()`, `_build_forward_detail_table()` builders
- [x] 3.6 Add direction dispatch in `query_analysis()`: backward → `_run_backward_pipeline()`, forward → `_run_forward_pipeline()`
- [x] 3.7 Add `query_station_options()` — returns ordered workcenter groups list

## 4. Backend Routes & EventFetcher

- [x] 4.1 Update `mid_section_defect_routes.py` — add `station` + `direction` query params to all endpoints, add station validation, add `GET /station-options` endpoint
- [x] 4.2 Update `trace_routes.py` — `_seed_resolve_mid_section_defect()` passes `station`; lineage stage uses direction to choose `resolve_full_genealogy()` vs `resolve_forward_tree()`; events stage passes direction for domain selection
- [x] 4.3 Add `downstream_rejects` domain to `event_fetcher.py` — in `SUPPORTED_EVENT_DOMAINS` and `_build_domain_sql()`, loading `mid_section_defect/downstream_rejects.sql`

## 5. Frontend — FilterBar & App

- [x] 5.1 Update `FilterBar.vue` — add station `<select>` dropdown (fetches from `/station-options` on mount), add direction toggle button group (反向追溯/正向追溯), emit station+direction via `update-filters`
- [x] 5.2 Update `App.vue` — add `station: '測試'` and `direction: 'backward'` to filters reactive, include in `buildFilterParams()`, add computed `isForward`, switch chart layout by direction, update page header to '製程不良追溯分析' with dynamic subtitle
- [x] 5.3 Update `useTraceProgress.js` — add `downstream_rejects` to `PROFILE_DOMAINS.mid_section_defect` for forward, update `collectAllContainerIds()` to support `children_map` for forward direction

## 6. Frontend — Direction-Aware Components

- [x] 6.1 Update `KpiCards.vue` — accept `direction` + `stationLabel` props, switch card labels between backward/forward modes
- [x] 6.2 Update `DetailTable.vue` — accept `direction` prop, switch column definitions between backward (existing) and forward (偵測設備, 偵測投入, 偵測不良, 下游到達站數, 下游不良總數, 下游不良率, 最差下游站)
- [x] 6.3 Add `.direction-toggle` styles to `style.css`

## 7. Remove TMTT Defect Page

- [x] 7.1 Delete `frontend/src/tmtt-defect/` directory
- [x] 7.2 Delete `src/mes_dashboard/routes/tmtt_defect_routes.py`
- [x] 7.3 Delete `src/mes_dashboard/services/tmtt_defect_service.py`
- [x] 7.4 Delete `src/mes_dashboard/sql/tmtt_defect/` directory
- [x] 7.5 Remove tmtt-defect registration from `nativeModuleRegistry.js`, `routeContracts.js`, `vite.config.js`, `page_status.json`, `routes/__init__.py`, `app.py`, `page_registry.py`, and all migration baseline/config files
- [x] 7.6 Delete related test files and update remaining tests referencing tmtt-defect

## 8. Config & Metadata

- [x] 8.1 Update `page_status.json` — rename mid-section-defect page name from '中段製程不良追溯' to '製程不良追溯分析', remove tmtt-defect entry

## 9. Verification

- [x] 9.1 Run `python -m pytest tests/test_mid_section_defect_*.py -v` — all 22 tests pass
- [x] 9.2 Run `cd frontend && node --test` — 69/69 frontend tests pass
- [x] 9.3 Run all change-relevant backend tests (app_factory, navigation_contract, full_modernization_gates, page_registry, portal_shell_wave_b_native_smoke) — 64/64 pass
- [x] 9.4 Verify backward compat: `station=測試, direction=backward` produces identical data (renamed columns) — 25,415 detail rows, DETECTION_EQUIPMENTNAME columns (no TMTT_), KPI/charts/genealogy all correct
- [x] 9.5 Verify forward basic: `station=成型 (order=4), direction=forward` → 8 downstream stations, 1,673 detail rows, downstream reject distribution: 測試 1.67%, 水吹砂 0.03%, 切彎腳 0.03%, 去膠 0.02%, 電鍍 0.01%, 移印 0.01%
