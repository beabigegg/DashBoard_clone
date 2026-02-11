# Portal Shell Route-View Migration: Wave B Native Smoke Checklist

Last updated: 2026-02-11  
Scope: Native shell routes (`/job-query`, `/excel-query`, `/query-tool`, `/tmtt-defect`)

## Execution Rules

- Wave B routes are now `native` and must remain no-iframe in shell content area.
- Any P0 smoke failure blocks release until resolved.
- `/excel-query` and `/query-tool` smoke must run under admin session.

## Per-Page Native Smoke Checklist

| Page | Shell Entry Path | Required Query Params | Key Interaction | Error Path | Export Path | Table Checkpoint | Chart Checkpoint | Filter Checkpoint | Interaction Checkpoint | Matrix Checkpoint | Expected Outcome | Automated Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Job Query | `/portal-shell/job-query` | `resource_ids, start_date, end_date` | Resource load -> query jobs -> open txn detail | Missing resource/date returns validation error | `/api/job-query/export` | Jobs/Txn table columns keep API order and empty-state text | N/A | Date/resource/search filters sync to URL | Selected job row loads txn table with stable state | N/A | Query/search/export remain usable in native route-view | `tests/test_portal_shell_wave_b_native_smoke.py::test_job_query_native_smoke_query_search_export`; `frontend/tests/portal-shell-wave-b-native-smoke.test.js` |
| Excel Query (Admin) | `/portal-shell/excel-query` | `table_name, search_column, return_columns` (+ upload) | Upload Excel -> detect type -> execute advanced query | Invalid file / missing required args returns validation error | `/api/excel-query/export-csv` | Result table columns and row count match response payload | N/A | Table/query/date filters sync to URL and persist on refresh | Upload/query/export flow keeps success/error feedback contract | N/A | Upload/detect/query/export parity preserved after native cutover | `tests/test_portal_shell_wave_b_native_smoke.py::test_excel_query_native_smoke_upload_detect_query_export`; `frontend/tests/portal-shell-wave-b-native-smoke.test.js` |
| Query Tool (Admin) | `/portal-shell/query-tool` | `input_type`, optional `workcenter_groups`, `equipment_ids`, date range | Resolve -> history -> associations -> equipment-period query | Missing input/container/type triggers deterministic errors | `/api/query-tool/export-csv` | Resolved/history/association/equipment tables stay query-consistent | N/A | Batch/equipment filters sync to URL with multi-value keys | Selection and association state transitions remain deterministic | N/A | Resolve/history/association/equipment workflows remain native-stable | `tests/test_portal_shell_wave_b_native_smoke.py::test_query_tool_native_smoke_resolve_history_association`; `frontend/tests/portal-shell-wave-b-native-smoke.test.js` |
| TMTT Defect | `/portal-shell/tmtt-defect` | `start_date, end_date` | Query -> pareto chart select -> detail sort/filter clear | Invalid/empty API payload shows fallback error banner | `/api/tmtt-defect/export` | Detail table sort/filter keeps scope continuity | Pareto/trend charts keep tooltip/legend/link state | Date range and active filter state preserved in view | Chart-table linked filtering resets correctly | N/A | TMTT chart-table parity and export remain stable in shell | `tests/test_portal_shell_wave_b_native_smoke.py::test_tmtt_defect_native_smoke_range_query_and_csv_export`; `frontend/tests/portal-shell-parity-table-chart-matrix.test.js` |

## No-Iframe Rule

- Shell content route-view must not render `<iframe>` for any Wave B route.
- Regression checks: `frontend/tests/portal-shell-no-iframe.test.js`, `tests/test_cutover_gates.py::test_g4_no_iframe_gate_blocks_if_shell_uses_iframe`.
