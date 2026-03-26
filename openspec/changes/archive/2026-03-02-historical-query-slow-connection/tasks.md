## 1. Core Infrastructure

- [x] 1.1 Add `DB_SLOW_CALL_TIMEOUT_MS` (default 300000) and `DB_SLOW_MAX_CONCURRENT` (default 3) to all config classes in `settings.py` (Config, DevelopmentConfig=2, ProductionConfig=3, TestingConfig=1/10000)
- [x] 1.2 Update `get_db_runtime_config()` in `database.py` to include `slow_call_timeout_ms` and `slow_max_concurrent`
- [x] 1.3 Add module-level `threading.Semaphore`, active count tracking, and `get_slow_query_active_count()` in `database.py`
- [x] 1.4 Refactor `read_sql_df_slow()`: default `timeout_seconds=None` (reads from config), acquire/release semaphore, log active count
- [x] 1.5 Update `dispose_engine()` to reset semaphore; add `slow_query_active` to `get_pool_status()`
- [x] 1.6 Increase Gunicorn timeout to 360s and graceful_timeout to 120s in `gunicorn.conf.py`

## 2. Backend Service Migration

- [x] 2.1 `reject_history_service.py`: change import to `read_sql_df_slow as read_sql_df`
- [x] 2.2 `reject_dataset_cache.py`: change import to `read_sql_df_slow as read_sql_df`
- [x] 2.3 `hold_history_service.py`: change import to `read_sql_df_slow as read_sql_df` (keep DatabaseCircuitOpenError/DatabasePoolExhaustedError imports)
- [x] 2.4 `resource_history_service.py`: change import to `read_sql_df_slow as read_sql_df`
- [x] 2.5 `job_query_service.py`: change import to `read_sql_df_slow as read_sql_df` (keep `get_db_connection` import)
- [x] 2.6 `excel_query_service.py`: set `connection.call_timeout = runtime["slow_call_timeout_ms"]` on direct connections in `execute_batch_query` and `execute_advanced_batch_query`
- [x] 2.7 `query_tool_service.py`: remove hardcoded `timeout_seconds=120` from `read_sql_df_slow` call (line 1131)

## 3. Frontend Timeout Updates

- [x] 3.1 `reject-history/App.vue`: `API_TIMEOUT` 60000 → 360000
- [x] 3.2 `mid-section-defect/App.vue`: `API_TIMEOUT` 120000 → 360000
- [x] 3.3 `hold-history/App.vue`: `API_TIMEOUT` 60000 → 360000
- [x] 3.4 `resource-history/App.vue`: `API_TIMEOUT` 60000 → 360000
- [x] 3.5 `shared-composables/useTraceProgress.js`: `DEFAULT_STAGE_TIMEOUT_MS` 60000 → 360000
- [x] 3.6 `job-query/composables/useJobQueryData.js`: all `timeout: 60000` → 360000 (3 sites)
- [x] 3.7 `excel-query/composables/useExcelQueryData.js`: `timeout: 120000` → 360000 (2 sites, lines 135, 255)
- [x] 3.8 `query-tool/composables/useLotDetail.js`: `timeout: 120000` → 360000 (3 sites) and `timeout: 60000` → 360000 (1 site)
- [x] 3.9 `query-tool/composables/useEquipmentQuery.js`: `timeout: 120000` → 360000 and `timeout: 60000` → 360000
- [x] 3.10 `query-tool/composables/useLotResolve.js`: `timeout: 60000` → 360000
- [x] 3.11 `query-tool/composables/useLotLineage.js`: `timeout: 60000` → 360000
- [x] 3.12 `query-tool/composables/useReverseLineage.js`: `timeout: 60000` → 360000
- [x] 3.13 `query-tool/components/LotJobsTable.vue`: `timeout: 60000` → 360000

## 4. Verification

- [x] 4.1 Run `python -m pytest tests/ -v` — all existing tests pass (28 pre-existing failures, 1076 passed, 0 new failures)
- [x] 4.2 Run `cd frontend && npm run build` — frontend builds successfully
