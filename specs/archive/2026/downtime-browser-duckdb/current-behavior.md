# Current Behavior: downtime-browser-duckdb (server-side pipeline baseline)

This captures the pre-change server-side compute path as the regression/parity baseline.
Reductions relocated to the browser must reproduce these results byte/row-equivalently.

## `POST /api/downtime-analysis/query` (current)

Route `downtime_analysis_routes.py::api_downtime_query` → `downtime_analysis_service.query_downtime_dataset`.

1. Build a deterministic `query_id` via `make_downtime_query_id()` (params + `DOWNTIME_BRIDGE_VERSION`, DA-06).
2. If `has_downtime_events(query_id)` (spool hit) → load the **fully-reduced** events parquet and return.
3. On miss: `execute_plan` (BatchQueryEngine, **whole-dataset single chunk** per ADR-0003) runs `base_events.sql` (E10 UDT/SDT/EGT fragments from `DWH.DW_MES_RESOURCESTATUS_SHIFT`) and `job_bridge.sql` (`DWH.DW_MES_JOB` + `JOBTXNHISTORY`) into a temp parquet.
4. Server-side Python reductions on the assembled frame:
   - `_merge_cross_shift_events` (DA-02) — sort by `(HISTORYID, OLDSTATUSNAME, OLDREASONNAME, OLDLASTSTATUSCHANGEDATE)`, detect run-breaks on key change or `>60s` gap, groupby cumsum, SUM(HOURS). A DuckDB-on-parquet variant (`_CROSS_SHIFT_MERGE_SQL` / `_merge_cross_shift_events_from_parquet`) already exists with a pandas fallback.
   - `_bridge_jobid` (Path A JOBID exact, Path B RESOURCEID==HISTORYID temporal-overlap tiebreak; `match_ambiguous` when runner-up ≥80%).
   - `_enrich_events_df` — `_map_big_category(OLDREASONNAME, OLDSTATUSNAME)` taxonomy (DA-04), wait/repair minutes (DA-05), `event_id` composite key.
5. Spool the **enriched** events frame (`store_downtime_events`, namespace `downtime_analysis_events`, TTL `DOWNTIME_ANALYSIS_CACHE_TTL`=72000s).
6. Response: `{query_id, summary, daily_trend, big_category, top_reasons}` (data-shape §3.12.1–3.12.4), all pre-aggregated server-side.

## OOM root cause

The whole-dataset reductions hold the full 184k-row frame in RAM and `_merge_cross_shift_events` / `_bridge_jobid` perform repeated `df.copy()` (service lines 216, 318, 338, 346, 359, 368–370, 383, 426, 440) plus the cross-product overlap join in `_bridge_jobid`. Peak RSS roughly doubles the base frame (~62 MB → 120 MB+) per concurrent request; under the constrained 6 GB/no-swap profile, concurrent or wide-range queries OOM-kill gunicorn workers. The DuckDB-on-parquet merge variant was added to mitigate the merge step but the bridge join and enrichment still run in pandas.

## 90-day Oracle fallback band-aid

`downtime_analysis_routes.py::_validate_dates` enforces `_MAX_ORACLE_DAYS = 90` (line 50): when the request is on the Oracle fallback path (outside the 3-month prewarm window) and the range exceeds 90 days, it returns 400. This is a deployed safety limit added solely to bound the OOM blast radius — orthogonal to the 730-day SYS-04/VAL-03 hard cap, which is enforced separately and stays.

## `/view`, `/equipment-detail`, `/event-detail` (current spool readers)

All three call `apply_view` (or `_build_equipment_detail_page` / `_build_event_detail_page`), which `load_downtime_events(query_id)` from the **enriched** spool and re-aggregate in pandas:
- `/view` → summary / daily_trend / big_category / top_reasons.
- `/equipment-detail` → paginated `EquipmentDetailRow[]` (wrapper key `equipment_detail`), optional `big_category`/`status_types` `.isin()` narrowing.
- `/event-detail` → paginated `EventDetailRow[]` (wrapper key `events`) with nullable `JobEnrichment`, optional `big_category`/`status_types`/`resource_id` narrowing.
- Export: `export_equipment_detail_csv` / `export_event_detail_csv` stream CSV (utf-8-sig) from the same enriched spool.

Every filter change today is a server round-trip re-reading the spool.

## 3-month DuckDB prewarm cache role

`downtime_analysis_duckdb_cache.py` maintains a rolling ~3-month server-side DuckDB cache of `base_events` + `job_data` (the raw Oracle pulls), file-locked across gunicorn workers. It feeds `execute_plan`'s Oracle-avoidance for queries inside the window; it does NOT contain reduced events. This layer is unchanged by this change.
