## 1. MSD Type B Contract Hardening

- [x] 1.1 Update `src/mes_dashboard/routes/mid_section_defect_routes.py` so detail spool miss returns `410 cache_expired` without calling `ensure_analysis_background_job()`.
- [x] 1.2 Update `src/mes_dashboard/routes/mid_section_defect_routes.py` so export spool miss returns `410 cache_expired` without calling `ensure_analysis_background_job()`.
- [x] 1.3 Add or update route tests covering MSD detail/export spool miss semantics and verifying no auto-dispatch side effect occurs.

## 2. Type A Bootstrap Failure Semantics

- [x] 2.1 Update `src/mes_dashboard/services/resource_dataset_cache.py` so `execute_primary_query()` returns an explicit failure when `apply_view()` cannot render the bootstrap response.
- [x] 2.2 Update `src/mes_dashboard/services/hold_dataset_cache.py` so `execute_primary_query()` returns an explicit failure when `apply_view()` cannot render the bootstrap response.
- [x] 2.3 Add or update tests covering resource/hold primary query behavior to distinguish runtime failure from legitimate empty datasets.

## 3. WIP Canonical Key Alignment

- [x] 3.1 Update `src/mes_dashboard/core/cache_updater.py` and `src/mes_dashboard/core/cache.py` to use the canonical WIP Parquet key naming rule without double prefixing.
- [x] 3.2 Update WIP availability checks and `src/mes_dashboard/routes/admin_routes.py` Redis memory sampling to inspect the same canonical `mes_wip:data:parquet` key.
- [x] 3.3 Add or update tests for WIP cache read/write, availability probe behavior, and admin telemetry key alignment.

## 4. Verification

- [x] 4.1 Run targeted backend tests for MSD routes, resource/hold dataset cache services, and WIP/admin cache observability paths.
- [x] 4.2 Manually verify the relevant OpenSpec scenarios against implementation behavior and record any deviations before archive.
