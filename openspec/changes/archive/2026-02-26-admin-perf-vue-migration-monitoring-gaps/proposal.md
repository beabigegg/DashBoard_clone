## Why

2026-02-25 server crash 暴露出管理員效能監控頁面在 pool 隔離架構變更後的關鍵盲區：slow query 並行數、slow-path 延遲、Worker 記憶體等核心指標既未收集也未顯示，導致 crash 前完全無法觀測系統真實負載。同時，`/admin/performance` 仍保留 1249 行的 Jinja template 作為 fallback，與已完成的 Vue SPA 遷移架構不一致，增加維護成本。

## What Changes

- **移除** Jinja template `templates/admin/performance.html`，`/admin/performance` 路由直接服務 Vue SPA（`static/dist/admin-performance.html`），不再有 fallback 邏輯
- **新增** `slow_query_active`、`slow_query_waiting`、`worker_rss_bytes` 三個欄位到 `metrics_history.sqlite` 快照，含 SQLite schema migration
- **新增** semaphore 排隊計數器（`_SLOW_QUERY_WAITING`），追蹤等待 slow query semaphore 的 thread 數量
- **修正** `read_sql_df_slow()` 和 `read_sql_df_slow_iter()` 將查詢延遲記錄到 `QueryMetrics`，使 P50/P95/P99 反映所有查詢路徑
- **新增** Vue SPA 連線池區塊顯示「慢查詢執行中」「慢查詢排隊中」指標 + 連線池趨勢圖加入 slow_query_active 線 + Worker 記憶體趨勢圖
- **新增** archive log 自動清理機制，整合到既有 `MetricsHistoryCollector` 的 cleanup cycle

## Capabilities

### New Capabilities

- `slow-query-observability`: 追蹤 slow query 並行數、排隊數、延遲，寫入 metrics history 並在前端顯示趨勢
- `worker-memory-tracking`: 追蹤 Worker RSS 記憶體，寫入 metrics history 並在前端顯示趨勢
- `archive-log-rotation`: logs/archive/ 目錄的自動清理機制，防止檔案無限增長

### Modified Capabilities

- `admin-performance-spa`: 移除 Jinja template fallback，完全遷移至 Vue SPA，新增 slow query 與記憶體監控面板
- `metrics-history-trending`: 擴充 snapshot schema 加入 slow_query_active、slow_query_waiting、worker_rss_bytes
- `connection-pool-monitoring`: 新增 semaphore 排隊計數器，slow-path 延遲納入 QueryMetrics

## Impact

- **後端**：`core/database.py`（排隊計數器 + latency 記錄）、`core/metrics_history.py`（schema 擴充 + archive cleanup）、`routes/admin_routes.py`（移除 fallback）
- **前端**：`frontend/src/admin-performance/App.vue`（新面板 + 趨勢圖）→ 需 rebuild
- **刪除**：`templates/admin/performance.html`（1249 行）
- **資料**：既有 `metrics_history.sqlite` 需 ALTER TABLE 加欄（向後相容，新欄位 nullable）
- **測試**：既有 `test_performance_integration.py` 已測試 SPA 路徑，無需修改；需新增 schema migration 測試
