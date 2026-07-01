# Cache & Spool Architecture Patterns

Promoted learnings from project history — pre-warm, parquet spool, DuckDB, and route-layer gotchas.

## Pre-warm Namespace Must Match Read Path

**The pre-warm must write to the same namespace/key pattern that user queries read from.** Writing to a separate prefix (e.g., `resource_history_prewarm`) while user queries read from `resource_dataset`/`resource_oee` provides zero cache benefit — the mismatch is silent and only discoverable by comparing logs across the two code paths.

Always trace the full read path of a live query before implementing a pre-warm.

Evidence: `resource-history-perf` — original prewarm used `cache_prefix="resource_history_prewarm"` via `batch_query_engine.execute_plan` while `resource_dataset_cache.py` wrote to `resource_dataset`/`resource_oee` via `register_spool_file()`.

## Multi-Worker Startup Lock

**Any gunicorn startup background task that loads data from Oracle must use a file-based exclusive lock** (`os.O_CREAT | os.O_EXCL` on a `.loading` sentinel file) to prevent all workers from executing the same Oracle query simultaneously.

Workers that lose the lock should poll `_try_reuse_existing()` in a loop (5 s intervals, 90 s timeout) until the winner finishes.

Pattern: `resource_history_duckdb_cache.py::_try_lock()` / `_release_lock()`

Evidence: `resource-history-perf` — without the lock, two gunicorn workers each ran the full 30 s Oracle prewarm concurrently.

## Parquet Schema Breaking Changes — Runbook + _SCHEMA_VERSION

Two complementary mechanisms; both apply when a spool service rewrites its parquet column schema (rename/add/remove):

**Rollback runbook (immediate recovery):** Add `rm tmp/query_spool/<service>/*.parquet` to the deploy runbook. Existing files become incompatible and hit schema-mismatch errors at the next `pd.read_parquet` / DuckDB `read_parquet` call. Document in `ci-gates.md §Rollback`.

**`_SCHEMA_VERSION` (zero-downtime forward deploys):** Embed a module-level `_SCHEMA_VERSION` integer in the query-id hash at write time. A redeploy that bumps `_SCHEMA_VERSION` orphans all in-flight parquets by key miss; readers rewrite automatically. Pin the bump in the **same commit** as the SQL/column change.

Pattern: `downtime_analysis_cache.py::_SCHEMA_VERSION`; `downtime_analysis_service.py::make_raw_spool_query_id`

Evidence: `prod-history-detail-raw-rows` (removed aggregated aliases); `downtime-browser-duckdb` (`data-shape-contract.md §3.13`).

**Embed-in-key inventory (verified query-arch A-4):** `reject_dataset`
(`_CACHE_SCHEMA_VERSION`), `resource_dataset` (`_CANONICAL_BASE_SCHEMA_VERSION`),
and `yield_alert_dataset` (`_CACHE_SCHEMA_VERSION`) all embed `cache_schema_version`
in the query-id at **every** `_make_query_id` call site — bumping the constant
orphans old parquet. `reject_dataset` is pinned against regression by
`tests/test_reject_schema_version_key.py` (AST guard over all call sites).
`hold_dataset` deliberately has **no** version constant: it uses DESCRIBE-based
column detection instead (see *hold-history Spool* below), so it tolerates schema
drift at read time without a key bump. (An earlier audit that flagged
`reject_dataset` as missing the embed was incorrect — the embed is present.)

## query-tool Has No Persistent Spool

**The query-tool executes Oracle SQL on-demand and does NOT persist DuckDB parquet files.** Do not add `rm tmp/query_spool/query_tool/*.parquet` to any deploy or rollback runbook for query-tool changes.

Evidence: `query-tool-partial-trackout` — `ci-gates.md §Rollback Policy` confirmed no parquet cleanup required even after adding `partial_count` to aggregated output.

## hold-history Spool — DESCRIBE-Based Column Detection

**`hold_history_sql_runtime._query_list` uses `DESCRIBE hold_src` at runtime** to detect whether a new column (e.g., `package`) exists in an existing parquet spool; it falls back to `NULL AS <col>` for old files. This avoids a `BinderException` without requiring a forced purge.

Apply this pattern when adding a nullable column to any hold-history SQL backed by a persistent spool.

Pattern: `hold_history_sql_runtime.py:477-598`

Evidence: `add-package-detail-tables`.

## SQL-to-API Rename Layer

**Report-module backends maintain a SQL `AS` alias layer (and pandas fallback rename dict) at the API boundary** that maps raw Oracle/spool column names to stable snake_case JSON keys. When renaming Oracle source columns or spool parquet columns, audit this layer first — if it already preserves the API JSON key, no frontend audit or contract change is needed.

Example: `production_history_sql_runtime.py:184-205, 242-251` maps `MFGORDERNAME → work_order`, `TRACKINTIMESTAMP → trackin_time`, etc.

Evidence: `prod-history-detail-raw-rows` — renamed 7 Oracle columns; frontend alias audit returned zero hits because the rename layer absorbed the change.

## SyncWorker Destructive Migration Guard

**Any `SyncWorker` migration that issues `TRUNCATE` or `DELETE FROM` on a live table must check `SELECT COUNT(*) ... LIMIT 1` first and skip the destructive statement when `row_count > 0`.** The migration-version `REPLACE` must still execute even when the destructive step is skipped, so the guard does not re-trigger on every restart.

A startup race (two gunicorn workers both passing the COUNT before either writes the version row) is acceptable because the version-meta `REPLACE` serializes subsequent runs; document this in a code comment.

Pattern: `SyncWorker._run_login_session_migration()`

Evidence: `fix-admin-dashboard` — without the guard, a redeploy truncated live `dashboard_login_sessions` on first startup.

## /api/resource/status/options — Independent Filter Dict

**`/api/resource/status/options` builds its own inline dict and does NOT call `query_resource_filter_options()`.** These two filter-option surfaces are maintained independently.

When adding a new filter field to the resource-status page, add it to BOTH:
1. `query_resource_filter_options()` in `resource_service.py`
2. The inline dict in the `/status/options` route handler in `resource_routes.py`

Adding only to the service causes a silent omission in the `/status/options` response.

Evidence: `resource-status-package-group` — `package_groups` had to be patched into the route's inline dict separately.

## Oracle CHAR Column Lookup — strip() on Both Sides

**When building a lookup dict keyed by an Oracle `CHAR` column, apply `str(value).strip()` at dict-build time AND again at each per-record lookup call.** Applying strip only at build time leaves lookups silently returning `None` when a live record's `CHAR` value has trailing spaces (CHAR pads to fixed width).

Pattern: `resource_cache.py::_load_package_group_lookup` (build) and `get_package_group_name` (lookup)

Evidence: `resource-status-package-group` — `test_package_group_lookup_char_trailing_space` confirms both sides required.

## Type-A Spool Frontend — Read success_response() for Exact Key

**When wiring a frontend composable to a `/view`, `/equipment-detail`, or `/event-detail`-style endpoint, verify the exact JSON wrapper key the backend returns before writing the composable.** A wrong key resolves to `undefined`, which the composable silently treats as an empty list — no error, just an empty table.

Read the route handler's `success_response(...)` call directly — do not infer the key from the service function name.

Evidence: `downtime-analysis-page` — fixed in commit `1931d26` (key was `events` not `rows`).

## Canonical Spool — Two-Phase Key Resolution

**Any service that adds a canonical spool must implement both phases in `try_compute_*_from_canonical_spool`:**

- **Phase 1 (superset):** if `[req_start, req_end] ⊆ [today-89d, today]` AND the warmup parquet exists, reuse the warmup key and inject date filters:
  - `WHERE "DATA_DATE" >= … AND "DATA_DATE" <= …` into the base temp view
  - `WHERE "SHIFT_DATE" >= … AND "SHIFT_DATE" <= …` into the OEE temp view
  - (`DATA_DATE` for base spool, `SHIFT_DATE` for OEE — do **not** apply uniformly)
- **Phase 2 (exact-match fallback):** look up `make_canonical_base_query_id(start_date, end_date)` directly; only this path hits Oracle on a miss.

Skipping Phase 1 causes queries within the warmup window to silently fall through to Oracle on every cache miss.

Pattern: `resource_history_sql_runtime.py:707-750`; `TestWarmupSupersetLookup`

Evidence: `resource-history-cache-fix`.

## spool_routes._ALLOWED_NAMESPACES — Security Whitelist

**Every new spool-using feature must add its namespace to `spool_routes.py:_ALLOWED_NAMESPACES` AND to `tests/test_spool_routes.py` in the same PR as the spool write.**

`GET /api/spool/<namespace>/…` returns HTTP 400 for any namespace not in the frozenset (path-traversal guard). Omitting a new namespace causes all parquet downloads for that feature to fail with 400 after deploy, even though data was written successfully.

Add the namespace to the `frozenset` in `spool_routes.py` AND to the `@pytest.mark.parametrize("ns", […])` list in `tests/test_spool_routes.py`.

Evidence: `downtime-browser-duckdb` — `downtime_analysis_base_events` and `downtime_analysis_job_bridge` omitted from whitelist; browser received HTTP 400 on every parquet download post-deploy.

## Type B Async — Coarse Bracket Milestones

**When a Type B RQ worker wraps a function that cannot accept a `progress_callback` (hard constraint: do not modify its signature), use coarse bracket milestones instead of per-chunk hash-mirroring.**

Emit in order: `pct=5` (worker started, before the call) → `pct=15` (entry confirmed) → `pct=90` (call returned successfully) → `pct=100` (job complete). This satisfies the required AC-4 ordering invariants: non-decreasing, first value ≤ 5, final value == 100.

Hash-mirroring (polling `get_batch_progress` from a background thread to extract per-chunk pct) is technically available but brittle — it couples the worker to engine internals and breaks on engine refactors. Only choose it when genuine per-chunk granularity is a hard QA requirement, and pin the hash recipe with a membership test.

Pattern: `src/mes_dashboard/services/hold_query_job_service.py` (hold-history Phase 3-B).  
Contrast: downtime Phase 3-A uses `5→15→60→90→100` with a mid-call emit — also coarse bracket, not hash-mirrored.  
Evidence: `specs/changes/hold-history-rq-async/archive.md` §Production Reality Findings #2.

## Spool-Schema "UNCHANGED" Assertion — Per-Path Column Documentation

**When a feature-flag migration introduces a new execution path that produces a different column set than the legacy path, document each path's actual columns separately in the `contracts/data/data-shape-contract.md` §3.x assertion. Writing a blanket "UNCHANGED" claim when the two paths diverge is a false contract.**

Required format: list "legacy path columns" and "unified path columns" as separate bullet points, note which column is absent and why (e.g., GROUP BY scope change in `post_aggregate`), and confirm whether any consumer reads the dropped column (determines breaking vs. non-breaking).

Pattern: `contracts/data/data-shape-contract.md §3.19` — `resource_oee` legacy includes `SHIFT_DATE`; unified `post_aggregate` drops it (GROUP BY EQUIPMENTID only, SHIFT_DATE absent from final parquet). Confirmed non-breaking because no consumer reads SHIFT_DATE from the OEE spool.

Evidence: `resource-history-migration` CR-2 — blanket UNCHANGED claim was caught as internally contradictory by contract-reviewer; fix required documenting per-path column sets explicitly.


## Coarse Spool Key — Fine-Filter Injection at DuckDB View Registration

When a spool is keyed on a subset of filter dimensions (e.g., `station + date`, excluding `pj_types`/`packages`), the DuckDB runtime wrapping it must inject the remaining fine-filter conditions as WHERE clauses inside `_register_runtime_views`, not at spool-write time. Omitting the clause causes every downstream view (Pareto chart, daily trend, LOT detail, KPI) to operate on full-spool data regardless of the active filter — a silent correctness failure with no error signal.

Filtering at spool-write time is the wrong fix: it forces a separate parquet per fine-filter combination and defeats coarse-key sharing. The coarse spool stays raw; fine-filter predicates are applied inside the DuckDB view registration layer.

**However**, the detection stage spool stored under `trace_query_id` (a finer key) **should** be saved pre-filtered, because `trace_query_id` is already specific to the filtered seed set. Apply the filter via pandas before writing the stage file so `get_detail()` and cached `get_summary()` reads are also filtered without needing to re-supply the filter params.

Pattern: `src/mes_dashboard/services/msd_duckdb_runtime.py::_register_runtime_views` — `WHERE TRIM(PJ_TYPE) IN (…)` added to `detection_raw` view; `src/mes_dashboard/services/trace_job_service.py::_build_job_msd_aggregation` — pandas filter before writing detection stage spool.

Evidence: `msd-type-package-filter` archive.md §Production Reality Findings Bug 2; commits 4a56ebcd.
