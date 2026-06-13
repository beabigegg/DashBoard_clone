# Design: downtime-browser-duckdb

## Summary
Move the downtime-analysis compute path from server-side pandas to browser-side DuckDB-WASM. The server stops running `_merge_cross_shift_events`, `_bridge_jobid`, and `_enrich_events_df` on the request path; instead it writes two **raw** spool parquets (`base_events` + `job_bridge`, one whole-dataset BQE chunk per ADR-0003) and returns their download URLs plus a taxonomy lookup table. The browser downloads both parquets once, runs the cross-shift merge, job-overlap bridge, category mapping, and all four views as local SQL — so filter changes become zero-round-trip local queries. This eliminates the gunicorn worker OOM (no full-frame pandas reduction server-side) and lets us remove the 90-day Oracle band-aid. The 3-month server-side DuckDB prewarm cache and the 730-day SYS-04 hard cap are unchanged.

## Affected Components
| component | file path(s) | nature of change |
|---|---|---|
| query route | `routes/downtime_analysis_routes.py` | `/query` returns URL+taxonomy shape; remove `_MAX_ORACLE_DAYS`/check in `_validate_dates`; `/view`,`/equipment-detail`,`/event-detail` marked deprecated (kept) |
| service | `services/downtime_analysis_service.py` | new raw-parquet spool writer; stop running reductions on request path; expose taxonomy builder; reductions retained as fallback only |
| events cache | `services/downtime_analysis_cache.py` | new raw namespaces + `SCHEMA_VERSION`; existing enriched namespace retained for fallback path |
| prewarm cache | `services/downtime_analysis_duckdb_cache.py` | unchanged (confirm only) — feeds raw-parquet write, not the API response |
| spool serving | `routes/spool_routes.py` | reuse existing `GET /api/spool/<namespace>/<query_id>.parquet` (no change) |
| SQL | `sql/downtime_analysis/base_events.sql`, `job_bridge.sql` | source of raw parquet columns; reconcile ORDER BY per ADR-0003 |
| frontend composable | `frontend/src/downtime-analysis/` (new `useDowntimeDuckDB.ts`) | download both parquets, run merge/bridge/views as DuckDB SQL |
| shared DuckDB core | `frontend/src/core/duckdb-client.ts`, `duckdb-activation-policy.ts` | read-only reuse (`fetchParquetBuffer`, `registerParquet`) |
| contracts | `contracts/api/*`, `data/*`, `business/*`, `CHANGELOG.md` | response-shape, raw-spool schema, relocated-reduction + limit-removal rules |

## Key Decisions

- **D1 — Deprecate `/view`, `/equipment-detail`, `/event-detail` in place.** Keep them alive for 2 minors, marked deprecated in api-inventory. Rationale: removing now is a breaking API change with no migration window and removes the only server-side fallback if browser DuckDB must be disabled. Rejected (remove now): forces a hard cutover with no rollback path; the enriched-spool reductions stay as the feature-flag fallback (Migration).
- **D2 — Browser-blob CSV export from the DuckDB-WASM result.** The browser already holds the full reduced dataset; exporting from it guarantees the CSV equals exactly what the user sees and uses zero server RAM (the OOM concern this change exists to fix). Rejected (server-side streaming from raw parquet): would require the server to re-run the relocated reductions just for export, re-introducing the pandas RAM cost on a large-export path. Keep `export_*_csv` as the deprecated fallback only.
- **D3 — Browser memory: hard load ceiling with explicit error, never a silent empty table.** Reuse `duckdb-activation-policy.ts` gating; if WASM init, parquet fetch, or a reduction query fails (or estimated buffer exceeds the policy ceiling), surface a visible error banner offering a narrower date range — per CLAUDE.md the Type-A silent-empty-table failure mode is forbidden. The composable must distinguish "zero rows" (valid empty) from "load/compute failed" (error path). No silent fallback to an empty render.
- **D4 — Parquet schema versioning via `SCHEMA_VERSION` constant folded into the spool cache key.** A `SCHEMA_VERSION` int in `downtime_analysis_cache.py` (distinct from `DOWNTIME_BRIDGE_VERSION`) participates in the raw-spool `query_id`; bumping it orphans old raw parquets by key so readers miss-and-rewrite rather than read an incompatible file. Post-deploy/rollback `rm -f tmp/query_spool/downtime_analysis/*.parquet` on any schema-breaking change (CLAUDE.md spool-schema-break rule). Rejected (DESCRIBE-based runtime column detection): viable for additive columns but the raw schema here is small and a clean version bump is simpler to reason about for a high-risk migration.
- **D5 — Deliver taxonomy as a JSON lookup table in the `/query` response.** Server stays single source of truth for `_map_big_category` (DA-04); browser applies it as a SQL join/CASE without a frontend rebuild when the taxonomy changes. Rejected (hard-code in TypeScript): forks the taxonomy across two languages and silently drifts on the next reason-code addition.
- **D6 — Prewarm cache role confirmed unchanged.** `downtime_analysis_duckdb_cache.py` continues feeding the raw-parquet write step (Oracle-avoidance for the 3-month window); it never serves the final API response. No code change beyond confirmation.
- **D7 — Two raw namespaces under the existing `downtime_analysis` dir** (ADR-0002): `downtime_analysis_base_events` and `downtime_analysis_job_bridge`. The enriched `downtime_analysis_events` namespace is retained for the deprecated/fallback path. ADR-0002's `DOWNTIME_BRIDGE_VERSION` invalidation lever still applies; `SCHEMA_VERSION` (D4) is the new raw-schema lever. A new ADR records the namespace split (see ADR note).
- **D8 — ADR-0003 compliance confirmed.** The raw spool write uses one whole-dataset BQE chunk (no `USE_ROW_COUNT_CHUNKING`); the browser receives the complete `base_events` parquet before running the cross-shift merge and job-overlap bridge, so no logical event is split at a chunk seam. ADR-0003 stays `accepted`; relocating the reductions to the browser does not enable row-count chunking.

## API Response Contract (`POST /api/downtime-analysis/query`, new shape)
```
{ base_spool_url: string,   // /api/spool/downtime_analysis_base_events/<query_id>.parquet
  jobs_spool_url: string,   // /api/spool/downtime_analysis_job_bridge/<query_id>.parquet
  query_id:       string,
  taxonomy: { map: [[reason, category], ...],   // exact-map rows
              prefixes: [[prefix, category], ...],  // e.g. ["TMTT_","檢查"]
              egt_category: "工程", fallback: "其他/未分類" } }
```
All four keys present and non-null for a valid query. The pre-aggregated `summary`/`daily_trend`/`big_category`/`top_reasons` keys are removed from this endpoint (now computed in-browser). 400 invalid/missing dates (730d cap retained); 500 Oracle error.

## Parquet Schema (raw spools, DuckDB types)
`base_events` (from `base_events.sql`): `HISTORYID VARCHAR`, `OLDSTATUSNAME VARCHAR`, `OLDREASONNAME VARCHAR`, `OLDLASTSTATUSCHANGEDATE TIMESTAMP`, `LASTSTATUSCHANGEDATE TIMESTAMP`, `HOURS DOUBLE`, `JOBID VARCHAR`.
`job_bridge` (from `job_bridge.sql`): `JOBID VARCHAR`, `RESOURCEID VARCHAR`, `CREATEDATE TIMESTAMP`, `COMPLETEDATE TIMESTAMP`, `SYMPTOMCODENAME VARCHAR`, `CAUSECODENAME VARCHAR`, `REPAIRCODENAME VARCHAR`, `COMPLETE_FULLNAME VARCHAR`, `FIRSTCLOCKONDATE TIMESTAMP`, `LASTCLOCKOFFDATE TIMESTAMP`, `JOBORDERNAME VARCHAR`, `JOBMODELNAME VARCHAR`, `ASSIGNED_DATE TIMESTAMP`, `ACK_DATE TIMESTAMP`, `INSPECT_START TIMESTAMP`, `INSPECT_END TIMESTAMP`.
Authoritative column source is the two SQL files; data-shape-contract §3.9-style raw-spool tables to be added by contract-reviewer.

## Migration / Rollback
Forward cutover is gated by a feature flag (env, e.g. `DOWNTIME_BROWSER_DUCKDB`). Default-on after parity sign-off. The deprecated server-side path (`apply_view` + enriched `downtime_analysis_events` spool + CSV streamers) is retained behind the flag-off branch as the rollback target: flipping the flag off restores the prior `{query_id, summary, ...}` response and server-rendered views with no redeploy. Roll back fully by reverting the flag and (if the raw schema shipped) running `rm -f tmp/query_spool/downtime_analysis/*.parquet` per D4. The 90-day `_MAX_ORACLE_DAYS` removal is only safe while the browser path is active; if rolled back to the server path under the 6 GB profile, re-introduce the limit or accept OOM risk on wide ranges — call this out in ci-gates §Rollback.

## Open Risks
- Browser/Python parity on the cross-shift merge tie-break and `_bridge_jobid` ambiguity rule (≥80% runner-up) — highest-correctness risk; ADR-0003 flags silent-corruption potential. Parity matrix on the 184k-row fixture is mandatory.
- Low-RAM clients on the 184k-row (~62 MB) parquet: D3 ceiling must be tuned against the activation policy; needs a real low-RAM device/profile test.
- Two-parquet atomicity: a `base` hit with a missing/expired `jobs` parquet must fail loudly (410-equivalent), not silently drop job enrichment.
