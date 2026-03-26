## 1. 後端：Semaphore 排隊計數器 + Slow-path latency

- [x] 1.1 在 `src/mes_dashboard/core/database.py` 新增 `_SLOW_QUERY_WAITING` counter 和 `get_slow_query_waiting_count()` 函數
- [x] 1.2 修改 `read_sql_df_slow()` 在 semaphore.acquire() 前後遞增/遞減 `_SLOW_QUERY_WAITING`
- [x] 1.3 修改 `read_sql_df_slow_iter()` 同上加入 waiting counter 邏輯
- [x] 1.4 修改 `get_pool_status()` 回傳中加入 `slow_query_waiting` 欄位
- [x] 1.5 在 `read_sql_df_slow()` finally block 呼叫 `record_query_latency(elapsed)`
- [x] 1.6 在 `read_sql_df_slow_iter()` finally block 呼叫 `record_query_latency(elapsed)`

## 2. 後端：metrics_history schema 擴充 + archive cleanup

- [x] 2.1 在 `src/mes_dashboard/core/metrics_history.py` 的 schema 新增 `slow_query_active INTEGER`, `slow_query_waiting INTEGER`, `worker_rss_bytes INTEGER` 欄位
- [x] 2.2 在 `MetricsHistoryStore.initialize()` 加入 ALTER TABLE ADD COLUMN migration（容錯 duplicate column）
- [x] 2.3 更新 `COLUMNS` list 加入新欄位
- [x] 2.4 更新 `write_snapshot()` 加入新欄位的讀取和 INSERT
- [x] 2.5 更新 `_collect_snapshot()` 收集 `slow_query_active`、`slow_query_waiting`（從 `get_pool_status()`）和 `worker_rss_bytes`（從 `resource.getrusage()`）
- [x] 2.6 新增 `cleanup_archive_logs(archive_dir, keep_per_type)` 函數，含 `ARCHIVE_LOG_DIR` 和 `ARCHIVE_LOG_KEEP_COUNT` env var 配置
- [x] 2.7 在 `MetricsHistoryCollector._run()` 的 cleanup cycle 呼叫 `cleanup_archive_logs()`

## 3. 後端：移除 Jinja fallback

- [x] 3.1 修改 `src/mes_dashboard/routes/admin_routes.py` 的 `performance()` 路由，移除 Jinja fallback 邏輯（改為直接 `send_from_directory`）
- [x] 3.2 刪除 `src/mes_dashboard/templates/admin/performance.html`
- [x] 3.3 更新 `scripts/check_full_modernization_gates.py` 將 `/admin/performance` 的 gate check 從 template 路徑改為 `frontend/src/admin-performance/style.css`

## 4. 前端：Vue SPA 新增監控面板

- [x] 4.1 在 `frontend/src/admin-performance/App.vue` 連線池 section 新增 `slow_query_active` 和 `slow_query_waiting` StatCards
- [x] 4.2 在 `poolTrendSeries` 加入 `slow_query_active` 趨勢線
- [x] 4.3 新增 `memoryTrendSeries` 定義和 Worker 記憶體 TrendChart 組件
- [x] 4.4 新增 `historyData` 預處理邏輯：將 `worker_rss_bytes` 轉為 `worker_rss_mb`

## 5. Build + 測試驗證

- [x] 5.1 執行 `cd frontend && npx vite build` 確認 build 成功
- [x] 5.2 執行 `python -m pytest tests/ -v --tb=short` 確認既有測試通過
- [x] 5.3 確認 `test_performance_page_loads` 測試通過（SPA 路徑驗證）
