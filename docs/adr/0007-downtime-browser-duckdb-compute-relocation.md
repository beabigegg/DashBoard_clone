# ADR 0007: Downtime Analysis compute relocated to browser DuckDB-WASM over raw spools

## Status
proposed

## Context
The released `/downtime-analysis` page computes everything server-side: `execute_plan` pulls raw E10 fragments + jobs, then Python runs `_merge_cross_shift_events` (DA-02), `_bridge_jobid`, and `_enrich_events_df` (DA-04/DA-05) on the full ~184k-row frame. Those whole-dataset reductions repeatedly `df.copy()` and run a cross-product overlap join, doubling peak RSS and OOM-killing gunicorn workers under the 6 GB/no-swap profile. A 90-day `_MAX_ORACLE_DAYS` band-aid was deployed solely to bound the blast radius. ADR-0003 already establishes these reductions require the *full* dataset and are silent-corruption-prone if split.

resource-history/hold-history/reject-history already prove a browser-DuckDB pattern: server writes a spool parquet, returns `/api/spool/<namespace>/<query_id>.parquet`, browser runs SQL locally via `frontend/src/core/duckdb-client.ts`.

## Decision
Relocate the downtime reductions (cross-shift merge, job-overlap bridge, big-category taxonomy, view aggregations) to browser DuckDB-WASM. The server writes two **raw** spool parquets — `downtime_analysis_base_events` and `downtime_analysis_job_bridge` (one whole-dataset BQE chunk, ADR-0003-compliant) — and `POST /query` returns `{base_spool_url, jobs_spool_url, query_id, taxonomy}`. The big-category taxonomy is delivered as a JSON lookup table so the server remains its single source of truth. The browser owns all reduction and view computation; filter changes are local SQL with zero round-trips. `_MAX_ORACLE_DAYS` (90d) is removed; the 730d SYS-04 cap stays. The legacy server-side path (enriched `downtime_analysis_events` spool + `/view`,`/equipment-detail`,`/event-detail` + CSV streamers) is deprecated-in-place for 2 minors behind a feature flag as the rollback target. A `SCHEMA_VERSION` constant in the raw-spool cache key governs raw-schema invalidation, independent of ADR-0002's `DOWNTIME_BRIDGE_VERSION`.

## Consequences
- OOM-causing pandas reductions leave the request path; server RAM per query drops to a raw spool write. CSV export moves to a browser blob (zero server RAM).
- Correctness now depends on browser SQL reproducing the Python reductions byte/row-equivalently — a mandatory parity gate on the 184k-row fixture; ADR-0003's seam-safety reasoning still governs.
- Low-RAM clients must download ~62 MB of parquet; a hard memory ceiling with a visible error (never a silent empty table) is required.
- Two-namespace raw spool: a `base` hit with a missing `jobs` parquet must fail loudly, not drop job enrichment.
- Reversal (returning compute to the server) must update this ADR to `superseded`, restore `_MAX_ORACLE_DAYS` under the constrained profile, and re-justify the OOM exposure — it must not happen silently via the still-present fallback path.
