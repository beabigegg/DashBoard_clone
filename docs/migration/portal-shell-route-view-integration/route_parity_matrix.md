# Route Parity Matrix (Shell Route-View Integration)

Generated at: `2026-02-11T07:44:03+00:00`

| Route | Mode | Required Query Keys | Table / Filter Focus | Chart / Matrix Focus | Owner | Rollback |
| --- | --- | --- | --- | --- | --- | --- |
| `/wip-overview` | `native` | `workorder, lotid, package, type, status` | table_files=2; sort=N; pagination=N | chart_files=1; legend=Y; tooltip=Y; matrix=Y | `frontend-mes-reporting` | `fallback_to_legacy_route` |
| `/wip-detail` | `native` | `workcenter, workorder, lotid, package, type, status` | table_files=1; sort=N; pagination=Y | chart_files=0; legend=N; tooltip=N; matrix=N | `frontend-mes-reporting` | `fallback_to_legacy_route` |
| `/hold-overview` | `native` | `-` | table_files=2; sort=Y; pagination=Y | chart_files=1; legend=Y; tooltip=Y; matrix=Y | `frontend-mes-reporting` | `fallback_to_legacy_route` |
| `/hold-detail` | `native` | `reason` | table_files=2; sort=N; pagination=Y | chart_files=0; legend=N; tooltip=N; matrix=N | `frontend-mes-reporting` | `fallback_to_legacy_route` |
| `/hold-history` | `native` | `-` | table_files=1; sort=N; pagination=Y | chart_files=3; legend=Y; tooltip=Y; matrix=N | `frontend-mes-reporting` | `fallback_to_legacy_route` |
| `/resource` | `native` | `-` | table_files=0; sort=Y; pagination=N | chart_files=0; legend=N; tooltip=Y; matrix=Y | `frontend-mes-reporting` | `fallback_to_legacy_route` |
| `/resource-history` | `native` | `start_date, end_date, granularity, workcenter_groups, families, resource_ids, is_production, is_key, is_monitor` | table_files=0; sort=Y; pagination=N | chart_files=4; legend=Y; tooltip=Y; matrix=Y | `frontend-mes-reporting` | `fallback_to_legacy_route` |
| `/qc-gate` | `native` | `-` | table_files=1; sort=Y; pagination=N | chart_files=2; legend=Y; tooltip=Y; matrix=N | `frontend-mes-reporting` | `fallback_to_legacy_route` |
| `/job-query` | `native` | `-` | table_files=2; sort=Y; pagination=N | chart_files=0; legend=N; tooltip=N; matrix=N | `frontend-mes-reporting` | `fallback_to_legacy_route` |
| `/excel-query` | `native` | `-` | table_files=2; sort=Y; pagination=N | chart_files=0; legend=N; tooltip=N; matrix=N | `frontend-mes-reporting` | `fallback_to_legacy_route` |
| `/query-tool` | `native` | `-` | table_files=2; sort=Y; pagination=N | chart_files=0; legend=Y; tooltip=Y; matrix=N | `frontend-mes-reporting` | `fallback_to_legacy_route` |
| `/tmtt-defect` | `native` | `-` | table_files=1; sort=Y; pagination=N | chart_files=1; legend=Y; tooltip=Y; matrix=N | `frontend-mes-reporting` | `fallback_to_legacy_route` |

## Notes

- Matrix and chart/table links are validated further in per-page smoke and parity tests.
- All target routes are in native mode; no iframe/wrapper runtime host remains in shell content path.
