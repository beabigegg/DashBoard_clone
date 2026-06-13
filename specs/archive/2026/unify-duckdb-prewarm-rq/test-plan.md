---
change-id: unify-duckdb-prewarm-rq
schema-version: 0.1.0
last-changed: 2026-06-12
risk: high
tier: 1
---

# Test Plan: unify-duckdb-prewarm-rq

## Acceptance Criteria — Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 (no daemon-thread start_duckdb_prewarm in app.py) | unit | `tests/test_app_startup.py` | 0 |
| AC-1 (RQ warmup enqueued at startup for both services) | integration | `tests/integration/test_preload_fork_safety.py` | 1 |
| AC-2 (loaded_at==today refresh gate — resource_history) | unit | `tests/test_resource_history_duckdb_cache.py` | 0 |
| AC-2 (loaded_at==today refresh gate — downtime_analysis) | unit | `tests/test_downtime_analysis_duckdb_cache.py` | 0 |
| AC-3 (downtime-analysis entry in _WARMUP_JOBS) | unit | `tests/test_spool_warmup_scheduler.py` | 0 |
| AC-4 (resource_history TTL == 72000 s) | unit | `tests/test_resource_history_duckdb_cache.py` | 0 |
| AC-4 (downtime_analysis TTL == 72000 s) | unit | `tests/test_downtime_analysis_duckdb_cache.py` | 0 |
| AC-4 (global CACHE_TTL_DATASET unchanged at 7200) | unit | `tests/test_env_contract.py` | 0 |
| AC-4 (env-var default pin: RESOURCE_HISTORY_SPOOL_TTL=72000) | contract | `tests/test_env_contract.py` | 1 |
| AC-4 (env-var default pin: DOWNTIME_ANALYSIS_CACHE_TTL=72000) | contract | `tests/test_env_contract.py` | 1 |
| AC-5 (query after daily refresh reads fresh parquet) | unit | `tests/test_resource_history_duckdb_cache.py` | 0 |
| AC-6 (multi-worker leader lock prevents duplicate Oracle prewarm) | integration | `tests/integration/test_preload_fork_safety.py` | 1 |
| AC-7 (RQ absent → Oracle fallback, no crash) | resilience | `tests/test_rq_warmup_resilience.py` | 1 |
| AC-7 (parquet readable after metadata-TTL expiry) | resilience | `tests/test_rq_warmup_resilience.py` | 1 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | TTL constants, _WARMUP_JOBS membership, loaded_at==today refresh gate, no daemon-thread symbol in app.py |
| contract | 1 | env-var default-value pins in test_env_contract.py; business-rules TTL rule presence check |
| integration | 1 | GunicornHarness: RQ warmup enqueued for both services; multi-worker leader-lock; no daemon-thread log lines |
| resilience | 1 | RQ worker absent → Oracle fallback; parquet readable past metadata-TTL expiry |

## New Test Names

**`tests/test_app_startup.py`** (new)
- `test_start_duckdb_prewarm_not_imported_in_app_module`
- `test_app_startup_does_not_register_daemon_prewarm_thread`

**`tests/test_spool_warmup_scheduler.py`** (extend or new)
- `test_downtime_analysis_in_warmup_jobs`
- `test_resource_history_in_warmup_jobs`
- `test_warmup_jobs_does_not_contain_production_history` (existing guard — must remain green)

**`tests/test_resource_history_duckdb_cache.py`** (extend)
- `test_spool_ttl_default_is_72000`
- `test_loaded_at_today_causes_refresh_skip`
- `test_loaded_at_yesterday_triggers_fresh_load`

**`tests/test_downtime_analysis_duckdb_cache.py`** (extend)
- `test_spool_ttl_default_is_72000`
- `test_loaded_at_today_causes_refresh_skip`
- `test_loaded_at_yesterday_triggers_fresh_load`

**`tests/test_env_contract.py`** (extend)
- `test_resource_history_spool_ttl_default_is_72000`
- `test_downtime_analysis_cache_ttl_default_is_72000`
- `test_resource_history_spool_ttl_documented_in_contract`
- `test_downtime_analysis_cache_ttl_documented_in_contract`
- `test_cache_ttl_dataset_unchanged_at_7200`

**`tests/test_rq_warmup_resilience.py`** (new)
- `test_resource_history_falls_back_to_oracle_when_rq_unavailable`
- `test_downtime_analysis_falls_back_to_oracle_when_rq_unavailable`
- `test_parquet_readable_after_metadata_ttl_expiry_resource_history`
- `test_parquet_readable_after_metadata_ttl_expiry_downtime_analysis`

**`tests/integration/test_preload_fork_safety.py`** (extend in-place)
- `test_rq_warmup_enqueued_for_resource_history_at_startup`
- `test_rq_warmup_enqueued_for_downtime_analysis_at_startup`
- `test_no_daemon_prewarm_thread_started_at_startup`
- Update `test_resource_history_duckdb_prewarm_runs_once` sentinel string to RQ enqueue log
- Update `test_downtime_prewarm_runs_once_across_two_workers` sentinel string to RQ enqueue log

## Out of Scope

- Daily-refresh + 20h-TTL boundary over a 24 h window (Tier 3 nightly soak; not pre-merge).
- Oracle query correctness for the prewarm load (covered by existing resource_history and downtime_analysis SQL runtime tests).
- Visual regression (no UI change).
- Stress / soak tests (promote only if post-deploy soak evidence is collected).

## Notes

- AC-1 absence test: inspect `app.py` AST or `importlib` attributes — avoid mock, which cannot detect a removed symbol.
- TTL constants frozen at import: if `os.getenv(...)` is module-level, tests must use `monkeypatch.setattr` not `monkeypatch.setenv`.
- `test_env_contract.py` pin tests must assert the imported constant value, not just that the var name appears in `env-contract.md`.
- GunicornHarness env isolation: pop `FLASK_ENV`/`FLASK_TESTING`/`PYTEST_CURRENT_TEST`, set `REDIS_ENABLED=true` (see conftest.py pattern).
- Existing integration tests for daemon-thread sentinel strings must be updated (not duplicated) once daemon threads are replaced by RQ enqueue log lines.
