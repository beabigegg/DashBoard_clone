# Design: material-part-consumption

## Summary
Adds a standalone read-only report page `/material-consumption` ("料號用量報表") as a full vertical slice: new Flask Blueprint + service + SQL + RQ worker, a new Vue SPA bundle in portal-shell, and a two-layer Redis+Parquet-spool+DuckDB cache pipeline mirroring `material_trace_service`. Two distinct spools are produced from one Oracle query family against `DW_MES_LOTMATERIALSHISTORY` (joined to `DWH.DW_MES_CONTAINER.PJ_TYPE`): a small **summary spool** stored at day-level so granularity (week/month/quarter) can be re-grouped in DuckDB without re-querying Oracle (same regroup mechanism as `resource_history_sql_runtime`), and a **detail spool** of raw rows for paginated browsing and chunked CSV export. The detail path runs async via a new dedicated RQ queue (`material-consumption`) when the result exceeds a configurable row threshold. No DB migration, no DuckDB prewarm.

## Affected Components
| component | file path(s) | nature of change |
|---|---|---|
| Route blueprint | `src/mes_dashboard/routes/material_consumption_routes.py` | NEW — 7 endpoints, success_response envelope |
| Service | `src/mes_dashboard/services/material_consumption_service.py` | NEW — Oracle aggregate → summary+detail spool, cache keys, RQ job fn |
| DuckDB runtime | `src/mes_dashboard/services/material_consumption_duckdb_runtime.py` | NEW — summary regroup + detail pagination + chunked CSV export |
| SQL | `src/mes_dashboard/sql/material_consumption/*.sql` | NEW — summary_by_day.sql, detail_rows.sql, filter_options.sql (PJ_TYPE join) |
| Blueprint registration | `src/mes_dashboard/routes/__init__.py` | MODIFY — import + `register_blueprint(material_consumption_bp)` + `__all__` |
| Admin RQ monitor | `src/mes_dashboard/services/rq_monitor_service.py` | MODIFY — add `os.getenv("MATERIAL_CONSUMPTION_WORKER_QUEUE","material-consumption")` to `_QUEUE_NAMES` |
| Page registry | `data/page_status.json` | MODIFY — add `/material-consumption` page object (drawer-2) |
| Asset readiness | `docs/migration/full-modernization-architecture-blueprint/asset_readiness_manifest.json` | MODIFY — map `/material-consumption` → dist asset (startup-validated; crash risk) |
| Route scope matrix | `docs/migration/full-modernization-architecture-blueprint/route_scope_matrix.json` | MODIFY — classify `/material-consumption` in-scope |
| Frontend SPA | `frontend/src/material-consumption/` | NEW — Vue3 app, components, echarts, scoped `.theme-material-consumption` CSS |
| Route contracts | `frontend/src/portal-shell/routeContracts.js` | MODIFY — add `/material-consumption` contract + in-scope list entry |
| RQ worker unit | `deploy/` (systemd unit + watchdog) | NEW — worker process for `material-consumption` queue |

## Key Decisions

- **Summary/detail spool split**: two spools from one query family, not one. Summary holds day-level aggregates (tiny, always-sync, drives KPI + trend + TYPE charts); detail holds raw rows (potentially large, async). — rejected single spool: would force the chart path to scan/aggregate millions of raw rows on every granularity switch, defeating the sub-millisecond regroup goal.
- **Granularity switch without Oracle re-query** (see ADR `docs/adr/0001-material-consumption-summary-spool-granularity-key.md`): `GET /view?query_id=X&granularity=Y` reads the summary spool and re-groups in DuckDB (`date_trunc`/`strftime` bucket, same pattern as `resource_history_sql_runtime._granularity_bucket_expr`). **The summary spool cache key EXCLUDES granularity** — one spool serves all granularities. — rejected re-querying Oracle on each granularity change: adds multi-second UX latency to a pure presentation toggle.
- **Summary spool granularity = (txn_date, MATERIALPARTNAME, PJ_TYPE)**: small enough for millisecond DuckDB regroup, rich enough for both the per-part trend lines and the BY-TYPE breakdown. — rejected storing individual transaction rows in the summary spool: that is exactly the detail spool, redundant and slow to regroup.
- **Multi-worker spool-write concurrency**: summary write (aggregate SQL, < 5s target, idempotent result) accepts last-write-wins. Detail write (raw rows, potentially slow) reuses the idempotency-check-before-write pattern from `material_trace_service.execute_to_spool()` — check `get_spool_file_path()` exists before executing Oracle.
- **Async threshold for detail**: sync if estimated/returned rows ≤ `SYNC_ROW_LIMIT` (env, default 30000); enqueue on the `material-consumption` RQ queue if larger. Summary is always sync.
- **RQ queue name `material-consumption`**: a new dedicated queue keeps this slice's load isolated from other report queues; requires a new systemd worker unit + watchdog and the `rq_monitor_service._QUEUE_NAMES` update so it surfaces in Admin Dashboard. — rejected reusing `trace-events`: would couple unrelated workloads and muddy queue-depth monitoring.
- **No DuckDB prewarm**: consumption data changes frequently; a prewarm would be stale quickly and add deploy complexity. Cold query hits Oracle once; Redis/spool cache covers subsequent requests and all granularity switches.
- **Parquet schema is a breaking-change surface**: any future column rename/add/remove orphans existing files. Deploy and rollback runbooks must run `rm -f tmp/query_spool/material_consumption/*.parquet`.

## Parquet Schema

Summary spool (`tmp/query_spool/material_consumption/summary-*.parquet`):

| column | type | column | type |
|---|---|---|---|
| txn_date | DATE | total_consumed | FLOAT |
| material_part | VARCHAR | total_required | FLOAT |
| pj_type | VARCHAR | lot_count | INT |
| primary_category | VARCHAR | workorder_count | INT |

Detail spool: same columns as `material_trace/forward_by_lot.sql` output plus `pj_type` (VARCHAR).

## API Surface
(Payload shapes belong in `contracts/api/api-contract.md`; all use `success_response`.)

| method | endpoint | purpose |
|---|---|---|
| GET | /api/material-consumption/filter-options | MATERIALPARTNAME / PJ_TYPE filter values |
| POST | /api/material-consumption/query | submit summary query → returns query_id (sync) |
| GET | /api/material-consumption/view?query_id=X&granularity=week\|month\|quarter | regroup summary spool in DuckDB (no Oracle) |
| POST | /api/material-consumption/detail | submit detail query (sync ≤ limit, else async job) |
| GET | /api/material-consumption/detail/page?query_id=X&page=N | paginate detail spool via DuckDB |
| GET | /api/material-consumption/detail/job/<job_id> | poll async detail job status |
| POST | /api/material-consumption/export | chunked CSV stream of detail spool |

## Migration / Rollback
No DB migration — read-only Oracle access. Spool cleanup `rm -f tmp/query_spool/material_consumption/*.parquet` must run on both deploy and rollback (schema is breaking-change surface; document in `ci-gates.md §Rollback Policy`). The new systemd RQ worker unit must be enabled before first request; rollback = stop + disable + remove the unit and its watchdog. On rollback, **remove the `/material-consumption` entry from `asset_readiness_manifest.json`** before redeploy or `app.py:_validate_in_scope_asset_readiness()` will crash gunicorn at startup on the missing dist asset; likewise remove the `data/page_status.json` entry so the drawer stops emitting "缺少 route contract".

## Open Risks
- `DW_MES_LOTMATERIALSHISTORY` is ~17.8M rows; multi-part wildcard summary aggregate must stay ≤ 5s or the "always sync" summary assumption breaks (validate in stress; consider date-range guardrails).
- 20-series cap is a frontend constraint; backend must defensively reject > 20 MATERIALPARTNAME values to bound chart payload and query cost.
- `material-consumption` worker unit absent at deploy = detail async jobs hang in queue; watchdog + Admin RQ monitor must alert on zero-worker-for-queue.
