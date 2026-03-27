## 1. Slow Pool 調整

- [x] 1.1 Update `config/settings.py` Production: DB_SLOW_POOL_SIZE=5, DB_SLOW_POOL_MAX_OVERFLOW=3, DB_SLOW_MAX_CONCURRENT=8
- [x] 1.2 Update `config/settings.py` Development: align pool size + overflow = semaphore
- [x] 1.3 Add circuit breaker check to `read_sql_df_slow` in `core/database.py` — call `get_database_circuit_breaker()`, check `allow_request()`, record success/failure
- [x] 1.4 Extend `_keepalive_worker` in `core/database.py` to ping slow engine in addition to main engine

## 2. Container Filter Cache

- [x] 2.1 Create `services/container_filter_cache.py` with combined SQL for PRODUCTLINENAME + PJ_TYPE from DW_MES_CONTAINER
- [x] 2.2 Implement `init()`, `get_packages()`, `get_pj_types()`, `refresh()` with L1 memory + L2 Redis, TTL 24hr
- [x] 2.3 Modify `production_history_service.get_type_options()` to delegate to `container_filter_cache.get_pj_types()`

## 3. Reason Filter Cache

- [x] 3.1 Create `services/reason_filter_cache.py` with SQL for LOSSREASONNAME from DW_MES_LOTREJECTHISTORY (last 365 days)
- [x] 3.2 Implement `init()`, `get_reject_reasons()`, `refresh()` with L1 memory + L2 Redis, TTL 24hr, fail-open on refresh error

## 4. Filter Consumer Migration

- [x] 4.1 Modify `reject_history_service.get_filter_options()` — read packages from container_filter_cache, reasons from reason_filter_cache; accept but ignore date params for backward compat
- [x] 4.2 Verify mid_section_defect_service available_loss_reasons can use reason_filter_cache for dropdown (note: in-query `available_loss_reasons` derived from detection_df stays as-is for accuracy)

## 5. Resource Status Constant + Direct Connection Removal

- [x] 5.1 Modify `resource_service.query_resource_filter_options()` — use `STATUS_CATEGORIES` constant for statuses instead of Oracle query
- [x] 5.2 Delete `sql/resource/distinct_statuses.sql`
- [x] 5.3 Move `resource_routes.api_resource_status_values()` logic to service layer, use `read_sql_df()` instead of `get_db_connection()`
- [x] 5.4 Refactor `database.py` `get_table_columns()`, `get_table_data()`, `get_table_column_metadata()` to use `engine.connect()` instead of `get_db_connection()`

## 6. TTL Unification

- [x] 6.1 Update `CACHE_TTL_FILTER_GENERAL` in `config/constants.py` from 3600 → 86400
- [x] 6.2 Update `resource_cache` TTL from 4hr → 24hr (align RESOURCE_SYNC_INTERVAL or cache TTL constant)

## 7. Cache Updater Integration

- [x] 7.1 Add `container_filter_cache.init()` and `reason_filter_cache.init()` to cache_updater startup sequence
- [x] 7.2 Add 24hr refresh tasks for container_filter_cache and reason_filter_cache with Redis distributed lock
- [x] 7.3 Ensure refresh failure isolation — one cache failure does not block others

## 8. Testing

- [x] 8.1 Add unit tests for container_filter_cache (init, get_packages, get_pj_types, refresh, fail-open)
- [x] 8.2 Add unit tests for reason_filter_cache (init, get_reject_reasons, refresh, fail-open)
- [x] 8.3 Update existing tests for modified services (reject_history, production_history, resource_service)
- [x] 8.4 Add test for read_sql_df_slow circuit breaker integration
- [x] 8.5 Run `pytest tests/ -v` — all tests pass
