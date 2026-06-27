# Design: add-db-scheduling-page

## Summary
Add a read-only "DB生產排程助手" page that, for every `D/B-START` lot in `DWH.DW_MES_LOT_V`, recommends the currently-running DB-process equipment for that lot's workflow. A new sync GET endpoint (`/api/db-scheduling/queue`) backed by a new route + service module returns one row per recommended equipment per lot; matching is primary-by-`WORKFLOWNAME` (DB-02) with a BOP-first-char fallback (DB-03), `matchSource` tagging the path taken. No new persistence, cache namespace, queue, or async path is introduced — the endpoint reuses the existing 5-min WIP cache view as its only data source. The frontend adds an isolated Vue app and registers a new "生產輔助" navigation drawer (order 7) via the code-side manifest.

## Affected Components
| component | file path(s) | nature of change |
|---|---|---|
| route (new) | `src/mes_dashboard/routes/db_scheduling_routes.py` | new Blueprint; `GET /api/db-scheduling/queue`, auth required, `success_response(data=rows)` |
| service (new) | `src/mes_dashboard/services/db_scheduling_service.py` | new; `get_db_scheduling_queue()`; build start-lot list, primary workflow match, BOP fallback, sort, shape rows |
| app factory | `src/mes_dashboard/app.py` | register `db_scheduling_bp` alongside existing blueprints (line ~904) |
| frontend app (new) | `frontend/src/db-scheduling/{App.vue,main.js,style.css}` | new isolated Vue app; queue table + matchSource badge + refresh button |
| portal nav | `frontend/src/portal-shell/navigationManifest.js` | add `production-assist` drawer (order 7) + DB排程助手 item |
| portal registry | `frontend/src/portal-shell/nativeModuleRegistry.js` | register `db-scheduling` module mount gate |
| portal router | `frontend/src/portal-shell/router.js` | add `/db-scheduling` route |
| nav status store | `data/page_status.json` | add route→status entry (per modernization policy) |
| migration manifests | `docs/migration/{asset_readiness_manifest.json,route_scope_matrix.json}` | add new page entry to BOTH |
| contracts (already drafted) | `contracts/{api,data,business,css}` | `DbSchedulingQueueResponse`, §3.22, DB-00..DB-05, css-inventory entry |

## Key Decisions

- **Data source = existing WIP cache view, not a fresh dedicated Oracle JOIN.** DB-05 and §3.22 both pin the source as the 5-min WIP cache over `DWH.DW_MES_LOT_V`. The service derives both the `D/B-START` start-lots and the ACTIVE running-equipment pool from the same in-memory cached DataFrame (`get_cached_wip_data()`), filtering/joining in pandas, with a direct `read_sql_df` fallback only on cache miss. Rejected: issuing the validated standalone `WITH start_lots ... LEFT JOIN running_eqp` SQL against Oracle on every request — it adds a second 5-min-divergent snapshot of the same view (staleness confusion, AC-7 read-only intent), an extra Oracle round-trip per page load, and a second copy of the DB-00 SPEC list to keep in sync. The validated SQL stays in the spec as the semantic reference for the pandas implementation. See ADR 0013.

- **BOP fallback computed in Python post-query, not in SQL.** The fallback only fires for lots that got zero primary matches, and routes on `SUBSTR(BOP,1,1)` into one of three SPEC groups. Expressing this as a second self-JOIN on the running-equipment pool with a `BOP_FIRST` predicate is atomic but couples three branch conditions into one query and obscures the "only when primary empty" precedence. Rejected the SQL form: post-query Python keeps DB-02 (primary) and DB-03 (fallback) as readable sequential stages and matches the cache-derived data-flow above (the join already happens in pandas).

- **`matchSource = "none"` lots emit zero rows.** Per §3.22 cardinality and DB-03, a lot with no primary match and a non-U/E/P (or null) BOP produces no row — not an error, not a placeholder row. The `"none"` enum value remains declared in the contract for forward-compatibility/consumer typing but is not currently emitted. Rejected: emitting a `matchSource:"none"` row with null equipment — it would force every consumer to filter and breaks the "group by lotId for per-lot views" contract guarantee.

- **No Redis cache layer for the endpoint itself.** The upstream WIP cache already absorbs the only expensive I/O; layering a second endpoint-level cache would introduce an independent TTL and a second staleness window over identical data. Rejected for the same staleness-confusion reason as the dedicated-JOIN option.

## Migration / Rollback
Purely additive, no schema/data migration. Forward: register the blueprint, ship the Vue app, add the drawer to `navigationManifest.js`, add the route→status entry to `page_status.json`, and update both migration manifests in `docs/migration/`. Rollback is a code revert plus removing the new page entry from `data/page_status.json` (it is never auto-removed on code deletion — see modernization policy) and from the two migration manifests. No queue, cache namespace, parquet schema, or Oracle object is created, so there is nothing to drain or `rm`. Because the endpoint reads the shared WIP cache, no cache pre-warm or namespace key change is required.

## Open Risks
- DB-00 SPEC list (12 SPECs) is duplicated between `business-rules.md` and the service constant; an addition/removal is a business-rules breaking change. Pin the list with a membership test so the two cannot silently drift.
- `EQUIPMENTS` is a multi-value column; the "one row per distinct equipment" fan-out (DB-02) must split it deterministically — confirm the cached view's `EQUIPMENTS` representation (single ID vs delimited list) during implementation, as the cardinality contract depends on it.
- Cache-miss fallback path must be exercised in tests: CI has no Redis, so the service must degrade to `read_sql_df` (or empty result) without 500ing.
