# Regression Report — production-achievement-overhaul

Durable evidence that this change's shared-surface touches (`core/spool_warmup_scheduler.py`, `services/filter_cache.py`, `core/permissions.py`, and the D6 chunk-boundary fix in `workers/production_achievement_worker.py`) do not regress other features that depend on the same infrastructure. All commands below were re-run directly against the current working tree (not re-quoted from an agent's earlier claim).

## 1. Warmup scheduler — other reports' warm-cache jobs unaffected

`command: conda run -n mes-dashboard python -m pytest tests/test_spool_warmup_scheduler.py -v` → **12 passed**

- `test_production_history_not_in_warmup_jobs` — **passed**. This is the load-bearing regression guard: it does a coarse substring scan for `"production"` to keep the unrelated, high-volume `production_history` report out of the warmup registry. Backend-engineer deliberately named this change's 2 new warmup jobs `_warmup_achievement_{today,yesterday}_job` / `warmup-achievement-{today,yesterday}` (dropping the `production_`/`production-` prefix, keeping `achievement`) specifically to avoid a false-positive collision with this scan — confirmed still passing with both new jobs registered.
- `test_resource_history_duckdb_in_warmup_jobs`, `test_downtime_analysis_duckdb_in_warmup_jobs` — **passed**. The other 2 DuckDB-backed warm-cache jobs sharing this same scheduler are unaffected by the 6→8 job-count growth.
- `test_warmup_jobs_total_count_after_duckdb_additions` — **passed**, updated in this change to assert 8 (was 6), and confirmed the count reflects reality, not a stale hardcode.
- `test_leader_lock_prevents_duplicate_enqueue`, `test_enqueue_called_sequentially`, `test_init_warmup_scheduler_starts_thread`, `test_run_warmup_cycle_returns_false_when_disabled` — **passed**. Core scheduler mechanics (Redis leader-election, sequential enqueue, disabled-flag short-circuit) are untouched by this change and remain correct with 8 jobs instead of 6.
- `test_warmup_jobs_include_production_achievement_today_and_yesterday`, `test_production_achievement_warmup_jobs_call_ensure_today_yesterday_loaded`, `test_production_achievement_warmup_job_failure_is_caught_and_logged` — **passed**. This change's own 2 new jobs, confirming registration, correct delegation, and fault isolation (one job's failure doesn't crash the cycle or block siblings).
- stress-soak-engineer additionally verified all 8 jobs share identical `job_timeout`/`result_ttl`/`failure_ttl` config (no privileged job type) and that a deliberately-slow or faulting sibling doesn't delay/block the 2 new achievement jobs under concurrent load (`tests/stress/test_production_achievement_stress.py::TestWarmupSchedulerEightJobsNoMonopolization`, 4 tests, stress-tier).

## 2. filter_cache — existing cache orchestration unaffected

`command: conda run -n mes-dashboard python -m pytest tests/test_filter_cache_generic.py -v` → **18 passed**

- `TestTTLExpiry` (4 tests), `TestStampedeProtection` (2 tests), `TestRedisDisabledFallback` (3 tests), `TestRedisL2Hit` (2 tests), `TestRedisMissFallbackToOracle` (2 tests), `TestCacheStatus` (2 tests) — all **passed**. These cover the shared `_load_cache()` orchestration used by every filter-option consumer in the app (shift codes, workcenter groups, and now package_lf_values); none regressed when the new 4th loader was added.
- `TestPackageLfValuesCache` (3 tests) — **passed**. This change's new loader correctly participates in the same TTL/stampede/Redis-L2/Oracle-fallback machinery as the pre-existing 3 loaders, not a parallel bespoke path.

## 3. Permission scope — `can_edit_targets` widened scope, unchanged semantics

`command: conda run -n mes-dashboard python -m pytest tests/test_production_achievement_permissions.py -v` → **6 passed**

- `test_whitelisted_user_allowed`, `test_non_whitelisted_user_denied`, `test_mysql_unreachable_fails_closed_deny`, `test_ops_disabled_fails_closed_deny`, `test_explicit_identifier_bypasses_session`, `test_distinct_from_admin_required` — all **passed**, unmodified by this change. `core/permissions.py`'s `can_edit_targets()` gates the 3 new settings tables' write endpoints with the exact same function, same fail-closed semantics, same table — confirmed via `git diff` during backend-engineer's implementation to be a **docstring-only** change (zero code lines added/removed). The widened scope is additive at the call-site level (6 new route handlers call the same gate), not a change to the gate's own logic.

## 4. D6 closing-chunk fix — historical correction is intentional and seam-scoped

`command: conda run -n mes-dashboard python -m pytest tests/test_production_achievement_unified_job.py -v -k "ChunkSeam or D6 or closing_chunk"` → **5 passed**

- `test_midnight_seam_group_produces_one_row_not_duplicate_keys`, `test_post_aggregate_sum_merges_same_key_across_chunks` — **passed**. Pre-existing chunk-seam re-aggregation behavior (unrelated to D6) is unaffected by widening the grain to include PACKAGE_LF.
- `test_closing_chunk_included_zero_leakage_next_day` — **passed**. The new D6 closing chunk (`[end_date+1 00:00:00, end_date+1 07:30:00)`) is included exactly once per query and contributes ONLY to the queried range's last day — confirmed zero leakage into `end_date+1`.
- `test_pre_fix_undercount_fixture_now_corrected` — **passed**. A fixture reproducing the pre-fix under-count (N-shift tail rows that used to be silently dropped because `chunk_end_excl` was date-only) now correctly includes those rows. This is the intended, in-scope historical correction — it changes only the previously-wrong total at the day/N-shift-tail seam, nothing else.
- `test_build_chunk_sql_binds_full_datetime_chunk_end_excl` — **passed**. Confirms every chunk (not just the new closing one) now binds a full `YYYY-MM-DD HH24:MI:SS` datetime, not date-only — the mechanism behind the fix.
- stress-soak-engineer additionally verified this holds at stress scale (30/90/180-day ranges, up to 181 chunks): the D6 closing chunk is included exactly once regardless of range size, and a full seam-straddling simulation across *every* day boundary (not just the closing one) confirms `2*n_days` distinct rows with zero duplication and zero leakage, sub-30ms even at 181 chunks (`tests/stress/test_chunk_boundary.py::TestProductionAchievementD6ClosingChunkStress`).

## Summary

| shared surface | regression tests | result |
|---|---|---|
| Warmup scheduler | 12 (this file) + 4 (stress) | 16/16 passed |
| filter_cache | 18 | 18/18 passed |
| Permission scope | 6 | 6/6 passed |
| D6 historical correction | 5 (this file) + stress-scale verification | 5/5 passed + stress-scale confirmed |

No regression found in any shared surface touched by this change.
