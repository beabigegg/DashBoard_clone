## 1. Frontend Toolchain Setup

- [x] 1.1 Install npm dependencies: `vue`, `@vitejs/plugin-vue`, `echarts`, `vue-echarts`
- [x] 1.2 Update `vite.config.js`: add Vue plugin, add `qc-gate` HTML entry point, add `vendor-vue` manual chunk

## 2. Backend API

- [x] 2.1 Create `services/qc_gate_service.py`: read WIP cache, filter SPECNAME by QC/GATE pattern, compute wait_hours and bucket classification, sort stations by SPEC_ORDER from filter_cache
- [x] 2.2 Create `routes/qc_gate_routes.py`: blueprint with `GET /api/qc-gate/summary` endpoint
- [x] 2.3 Register blueprint in `routes/__init__.py` and add Flask route `GET /qc-gate` serving static HTML via `send_from_directory`

## 3. Vue Frontend Page

- [x] 3.1 Create `frontend/src/qc-gate/index.html`: standalone HTML entry with Vue app mount point
- [x] 3.2 Create `frontend/src/qc-gate/main.js`: Vue app bootstrap with createApp and mount
- [x] 3.3 Create `frontend/src/qc-gate/App.vue`: root layout with header (title, cache time, refresh button), chart area, and table area
- [x] 3.4 Create `frontend/src/qc-gate/composables/useQcGateData.js`: data fetching, 10min auto-refresh with visibilitychange, reactive state management
- [x] 3.5 Create `frontend/src/qc-gate/components/QcGateChart.vue`: ECharts stacked bar chart (x=station, y=count, stacked by 4 time buckets with color coding)
- [x] 3.6 Create `frontend/src/qc-gate/components/LotTable.vue`: sortable lot table with click-to-filter from chart, filter indicator, clear filter
- [x] 3.7 Create `frontend/src/qc-gate/style.css`: page styling consistent with existing dashboard aesthetic

## 4. Page Registration & Integration

- [x] 4.1 Register qc-gate page in `page_status.json`: route `/qc-gate`, name `QC-GATE 狀態`, drawer_id `reports`, status `released`
- [x] 4.2 Build frontend (`npm run build`) and verify output files exist in `static/dist/`

## 5. Verification

- [x] 5.1 Verify API endpoint returns correct data structure with QC-GATE filtered lots, wait time buckets, and station ordering
- [x] 5.2 Verify page renders in portal iframe: chart displays, table populates, click-to-filter works, auto-refresh fires
- [x] 5.3 Verify existing pages still build and function correctly (Vue plugin does not break vanilla JS entries)
