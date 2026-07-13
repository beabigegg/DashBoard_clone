# Design: add-uph-performance-page

## Summary
A net-new always-async report page `/uph-performance` (production-assist drawer,
order 3) that extracts Die-Bond (GDBA) / Wire-Bond (GWBA) UPH from
`DWH.EAP_EVENT ⋈ EAP_EVENT_DETAIL`. It is a vertical slice modeled directly on the
shipped `eap-alarm` (EAP-table access, container bridge, coarse-spool + DuckDB
derived views) and `production-achievement` (BaseChunkedDuckDBJob async shell)
features. Architecturally it adds one new `BaseChunkedDuckDBJob` subclass, one new
spool namespace + parquet schema (schema_version 1), one new `*_USE_UNIFIED_JOB`
env flag, and 7 new read endpoints — all additive, no existing behavior changed.
The load-bearing decisions (single family-conditional JOIN template, append path,
DB/WB via workcenter_groups) are captured in ADR-0017 and business rules UPH-01..05.

## Affected Components
| component | file path(s) | nature of change |
|---|---|---|
| new chunked worker | `src/mes_dashboard/workers/uph_performance_worker.py` (new) | `UphPerformanceJob(BaseChunkedDuckDBJob)`; `execute_uph_performance_unified_job` entry; `register_job_type` |
| shared Oracle SQL | `src/mes_dashboard/sql/uph_performance.sql` (new) | single JOIN'd chunk query; `{{ }}` placeholders for coarse filters |
| spool/cache service | `src/mes_dashboard/services/uph_performance_cache.py` (new) | `make_uph_performance_spool_key`, spool path, `_SCHEMA_VERSION=1` |
| view/query service | `src/mes_dashboard/services/uph_performance_service.py` (new) | DuckDB-derived trend/ranking/detail/filter-option views over the spool |
| DB/WB classifier (reuse) | `src/mes_dashboard/config/workcenter_groups.py` | called read-only via `get_workcenter_group()`; no edit |
| routes | `src/mes_dashboard/routes/uph_performance_routes.py` (new) | 7 endpoints; `spool_routes._ALLOWED_NAMESPACES += uph_performance` |
| deploy/launcher | `deploy/mes-dashboard-uph-performance-worker.service` (new), `scripts/start_server.sh` | new RQ worker wiring (no `--job-execution-timeout`) |
| contracts | api / data §3.29 / business / env / ci (already updated) | endpoints, parquet schema, UPH-01..05/UPH-ASYNC, env flag, deploy checklist |

## Key Decisions
- **Single shared `uph_performance.sql` with a family-conditional CASE detail JOIN** (ADR-0017):
  the `EAP_EVENT_DETAIL` JOIN picks `PARAMETER_NAME` via
  `d.PARAMETER_NAME = CASE SUBSTR(EQUIPMENT_ID,1,4) WHEN 'GDBA' THEN 'BondUPH' WHEN 'GWBA' THEN 'fHCM_UPH' END`
  in the ON clause → **rejected: blanket `PARAMETER_NAME IN ('BondUPH','fHCM_UPH')`** because it would let
  `BondUPH` attach to a GWBA event sharing a SEQ_ID — silent cross-family leak (UPH-03 forbids).
  → **rejected: two separate GDBA/GWBA passes unioned in post_aggregate** because it doubles Oracle
  round-trips for zero benefit — there is no cross-family aggregation, and each M[60] event carries
  exactly one UPH param (no EAV pivot needed, unlike eap-alarm's multi-param detail).
- **Chunking: `chunk_strategy=TIME`, ≤6h windows, `max_parallel=3`** matching eap-alarm/production-achievement.
  The detail JOIN over 24h previously timed out >180s; ≤6h runs 2–12s. An exact-match `PARAMETER_NAME`
  predicate (not `LIKE '%UPH%'`) further bounds detail cardinality. → rejected: single unchunked full-range
  query (forbidden, UPH-01).
- **`requires_cross_chunk_reduction=False` (append path)** like `EapAlarmJob`: each event row is
  independent, no seam-straddling group. `post_aggregate` = plain concat + the two enrichment bridges.
  → rejected: production-achievement-style re-aggregation, which is only needed for its SPECNAME
  shift-tail seam (ADR-0016) and does not apply here.
- **DB/WB label via `workcenter_groups.get_workcenter_group(WORKCENTERNAME)` in the worker's
  `post_aggregate` (Python layer)** — the `EQUIPMENT_ID`→`DW_MES_RESOURCE.RESOURCENAME`
  (`OBJECTCATEGORY='ASSEMBLY'`) bridge yields WORKCENTERNAME, then `get_workcenter_group()[0]` maps it;
  keep the result only if it is `焊接_DB`/`焊接_WB`, else `DB_WB_LABEL=NULL`. This runs in Python
  because `workcenter_groups` uses case-insensitive substring matching that cannot express cleanly in
  Oracle SQL. → **rejected: EQUIPMENT_ID prefix enumeration (GDBA%→DB / GWBA%→WB)**, retired in
  production per EA-07 / UPH-05 because the closed enum never matched real data.
- **Enrichment bridges in `post_aggregate`, not inline** in the chunk SQL (mirrors eap_alarm's
  `_safe_lot_product_df`): chunked `IN`-list lookups over distinct LOT_IDs / EQUIPMENT_IDs. Coarse user
  filters (package/type/workcenter) stay inline `EXISTS` semi-joins per data-shape §3.29.
- **Spool key composition is sufficient as specified in data-shape §3.29** — no adjustment needed. It
  covers date range + families + workcenter_names + packages + pj_types + equipment_ids + `_SCHEMA_VERSION`.
  The ranking block's own Type filter is deliberately NOT in the key (it re-slices the global-scope spool
  client-of-spool, per interaction-design and §3.29 Ranking).

## Pre-build exploratory probe (UPH-03 — backend-engineer, do this FIRST)
Before writing any worker/SQL code, backend-engineer MUST run a one-time read-only Oracle probe (per
docs/architecture/eap-event-uph-collection-investigation.md; read-only creds, `LAST_UPDATE_TIME` window
≤6h) confirming that `BondUPH` (GDBA) and `fHCM_UPH` (GWBA) each return non-empty `PARAMETER_VALUE` rows.
`BondUPH`/`fHCM_UPH` were recently reconfigured on the equipment side and intentionally differ from the
`UPHBonded` the earlier investigation saw — do NOT "correct" them back (UPH-03).
- If **both** return data → proceed with full build.
- If **either** returns empty → STOP and report to the user; do NOT swap parameter names. The likely cause
  is that the (recently-configured, especially GWBA) parameter is not yet collecting. The page can still
  ship because runtime empty is a graceful `state-empty` (not an error), but the probe result is durable
  risk evidence for qa-report.md and the user must decide: wait for data, ship with a known-empty family,
  or open a new contract change to adjust the parameter name.

## Migration / Rollback
Net-new page, net-new spool namespace, net-new parquet schema (`_SCHEMA_VERSION=1`) — no data migration.
Rollback is trivial and non-destructive: set `UPH_PERFORMANCE_USE_UNIFIED_JOB=off` (pure kill switch —
no legacy path exists, so spool-miss → 503, mirroring production-achievement), and/or
`rm -f tmp/query_spool/uph_performance/*.parquet` to drop the namespace dir. No other feature reads the
namespace, so removal cannot orphan or corrupt shared state. Any future parquet column add/remove/rename
requires bumping `_SCHEMA_VERSION` in the same commit (data-shape §3.29 breaking-change surface).

## Open Risks
- **Shared 3-slot semaphore, 4th consumer (monitoring, not a fix in this change).** `UphPerformanceJob`
  inherits `BaseChunkedDuckDBJob.run()`, which brackets the Oracle fan-out in `heavy_query_slot`
  (`global_concurrency`, `MAX_CONCURRENT=3`; ADR-0011). The worker MUST NOT re-acquire the slot itself.
  It becomes a 4th heavy consumer alongside eap-alarm, production-achievement, and the other
  BaseChunkedDuckDBJob subclasses that share the same global cap. Per the user's explicit non-goal, this
  change does NOT touch `HEAVY_QUERY_MAX_CONCURRENT`, `max_parallel`, or RQ worker process count — but
  adding a heavy consumer of a 12M-row/day table onto an already-contended 3-slot gate is a real
  contention risk. Flagged for **stress-soak-engineer** to measure queue-wait/peak-concurrent under the
  new load; concurrency-knob uplift is a separate future architecture change.
- **GWBA data-availability (UPH-03).** Carried from the probe above; if `fHCM_UPH` is empty at build time,
  the Wire-Bond half of the page ships as a permanent empty state until the equipment collects data.
- **DB/WB NULL rate.** GDBA/GWBA machines whose WORKCENTERNAME does not match a `焊接_DB`/`焊接_WB`
  pattern (or has no DW_MES_RESOURCE match) render a NULL DB/WB label by design — acceptable per UPH-05,
  but a high NULL rate would blunt the ranking block's DB/WB adornment; worth spot-checking during the probe.
