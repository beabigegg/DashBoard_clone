# Tasks: Overnight Error Log Fixes

## 1. Fix broken import — `_get_resource_lookup` / `_get_workcenter_mapping` (P0)

- [x] 1.1 Add `_get_resource_lookup()` wrapper in `resource_dataset_cache.py` that delegates to `resource_history_service._get_filtered_resources()` + `_build_resource_lookup()`
- [x] 1.2 Add `_get_workcenter_mapping()` wrapper in `resource_dataset_cache.py` that re-exports `filter_cache.get_workcenter_mapping()`
- [x] 1.3 Verify `resource_history_sql_runtime.py:534` import resolves (run import in test)
- [x] 1.4 Verify `resource_history_routes.py:74` import resolves
- [x] 1.5 Verify `tests/e2e/test_resource_history_e2e.py` `@patch` targets resolve
- [x] 1.6 Run `pytest tests/test_resource_history_service.py tests/test_resource_history_sql_parity.py -v` to confirm no regressions

## 2. Graceful cache_updater shutdown (P1)

- [x] 2.1 Add `_CACHE_UPDATER_STOP` event and `_CACHE_UPDATER_THREAD` ref in `cache_updater.py`
- [x] 2.2 Refactor cache_updater thread loop to check stop event (replace `time.sleep` with `event.wait(timeout=interval)`)
- [x] 2.3 Export `stop_cache_updater()` function from `cache_updater.py` (set event + join with timeout=5)
- [x] 2.4 Call `stop_cache_updater()` from `database.py:dispose_engine()` before engine disposal (after `stop_keepalive()`, before health engine dispose)
- [x] 2.5 Add test: `stop_cache_updater()` when thread is running → thread stops within 5s
- [x] 2.6 Add test: `stop_cache_updater()` when thread not started → no-op, no exception

## 3. Reduce slow query log noise (P2)

- [x] 3.1 Change `database.py:832` threshold from `1.0` to `3.0`
- [x] 3.2 Update any existing tests that assert on the 1.0s threshold value
- [x] 3.3 Run `pytest tests/test_database_slow_pool.py tests/test_database_slow_iter.py -v`

## 4. Downgrade spool seed contention log level (P2)

- [x] 4.1 In `anomaly_detection_scheduler.py:164-165`, check for `single_flight_timeout` in exception message and log as WARNING instead of ERROR
- [x] 4.2 Add test: spool seed with `single_flight_timeout` exception logs at WARNING
- [x] 4.3 Add test: spool seed with other exception logs at ERROR (unchanged)

## 5. Verification

- [x] 5.1 Run full test suite: `pytest tests/ -v`
- [x] 5.2 Start server and confirm no ERROR/WARNING during single-worker startup

## 6. Post-verify fixes (from opsx:verify)

- [x] 6.1 Fix `cache_updater.stop()` — log WARNING when thread is still alive after join(5) instead of unconditional INFO
- [x] 6.2 Add test: `stop()` with hung thread (join is no-op) → WARNING logged (spec scenario 2)
