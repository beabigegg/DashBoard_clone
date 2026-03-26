## 1. Config 調整

- [x] 1.1 `settings.py`: Config base `DB_SLOW_MAX_CONCURRENT` 3→5, DevelopmentConfig 2→3, ProductionConfig 3→5

## 2. 後端 service 遷移

- [x] 2.1 `event_fetcher.py`: import `read_sql_df_slow as read_sql_df` (line 16)
- [x] 2.2 `event_fetcher.py`: `EVENT_FETCHER_MAX_WORKERS` default 4→2 (line 22)
- [x] 2.3 `event_fetcher.py`: `_fetch_batch` 加 `timeout_seconds=60` (line 247)
- [x] 2.4 `event_fetcher.py`: 新增 `CACHE_SKIP_CID_THRESHOLD`，`fetch_events` 大 CID 集跳過 cache + `del grouped`
- [x] 2.5 `lineage_engine.py`: import `read_sql_df_slow as read_sql_df` (line 10)

## 3. Route 層修改

- [x] 3.1 `trace_routes.py`: `TRACE_EVENTS_MAX_WORKERS` default 4→2 (line 39)
- [x] 3.2 `trace_routes.py`: events endpoint 中 `del raw_domain_results` 早期釋放
- [x] 3.3 `trace_routes.py`: 大查詢後 `gc.collect()`
- [x] 3.4 `trace_routes.py`: 大查詢跳過 route-level events cache

## 4. Tests

- [x] 4.1 `test_event_fetcher.py`: 新增 regression test 驗證 slow path import
- [x] 4.2 `test_lineage_engine.py`: 新增 regression test 驗證 slow path import
- [x] 4.3 執行 `pytest tests/ -v` 確認全部通過
