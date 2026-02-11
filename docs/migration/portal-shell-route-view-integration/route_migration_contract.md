# Route Migration Contract Freeze

Generated at: `2026-02-11T07:44:03+00:00`

This contract freezes route ownership and migration mode for shell cutover governance.

| Route ID | Route | Mode | Required Query Keys | Owner | Rollback Strategy |
| --- | --- | --- | --- | --- | --- |
| `wip-overview` | `/wip-overview` | `native` | `workorder, lotid, package, type, status` | `frontend-mes-reporting` | `fallback_to_legacy_route` |
| `wip-detail` | `/wip-detail` | `native` | `workcenter, workorder, lotid, package, type, status` | `frontend-mes-reporting` | `fallback_to_legacy_route` |
| `hold-overview` | `/hold-overview` | `native` | `-` | `frontend-mes-reporting` | `fallback_to_legacy_route` |
| `hold-detail` | `/hold-detail` | `native` | `reason` | `frontend-mes-reporting` | `fallback_to_legacy_route` |
| `hold-history` | `/hold-history` | `native` | `-` | `frontend-mes-reporting` | `fallback_to_legacy_route` |
| `resource` | `/resource` | `native` | `-` | `frontend-mes-reporting` | `fallback_to_legacy_route` |
| `resource-history` | `/resource-history` | `native` | `start_date, end_date, granularity, workcenter_groups, families, resource_ids, is_production, is_key, is_monitor` | `frontend-mes-reporting` | `fallback_to_legacy_route` |
| `qc-gate` | `/qc-gate` | `native` | `-` | `frontend-mes-reporting` | `fallback_to_legacy_route` |
| `job-query` | `/job-query` | `native` | `-` | `frontend-mes-reporting` | `fallback_to_legacy_route` |
| `excel-query` | `/excel-query` | `native` | `-` | `frontend-mes-reporting` | `fallback_to_legacy_route` |
| `query-tool` | `/query-tool` | `native` | `-` | `frontend-mes-reporting` | `fallback_to_legacy_route` |
| `tmtt-defect` | `/tmtt-defect` | `native` | `-` | `frontend-mes-reporting` | `fallback_to_legacy_route` |

## Validation Rules

- Missing route definitions are treated as blocking contract errors.
- Duplicate route definitions are rejected.
- `render_mode` MUST be `native` or `wrapper`.
- `owner` and `rollback_strategy` MUST be non-empty.
