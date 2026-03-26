## 1. Rate Limit for POST /query

- [x] 1.1 在 `reject_history_routes.py` 中新增 `_REJECT_HISTORY_QUERY_RATE_LIMIT = configured_rate_limit(bucket="reject-history-query", default_max_attempts=10, default_window_seconds=60)`（line ~60）
- [x] 1.2 在 `api_reject_history_query()` 函式加上 `@_REJECT_HISTORY_QUERY_RATE_LIMIT` 裝飾器（line 584）
- [x] 1.3 在 `.env` 新增 `REJECT_HISTORY_QUERY_RATE_LIMIT_MAX_REQUESTS=10` 和 `REJECT_HISTORY_QUERY_RATE_LIMIT_WINDOW_SECONDS=60`

## 2. RSS 前置檢查

- [x] 2.1 在 `reject_dataset_cache.py` 頂部新增 `REJECT_QUERY_RSS_REJECT_MB = float(os.getenv("REJECT_QUERY_RSS_REJECT_MB", "900"))` 及 import `process_rss_mb`
- [x] 2.2 在 `execute_primary_query()` 開頭（查詢鎖之前）加入 RSS 檢查邏輯：若 RSS ≥ 閾值則 raise `RejectPrimaryQueryOverloadError(code="SERVICE_OVERLOADED", retry_after=30)`
- [x] 2.3 在 `.env` 新增 `REJECT_QUERY_RSS_REJECT_MB=900`

## 3. SQL 層 max_rows_per_chunk 強制執行

- [x] 3.1 修改 `reject_dataset_cache.py` 的 `_run_reject_chunk()` 函式（line 700-706），將 debug log 替換為 `chunk_sql = f"SELECT * FROM ({chunk_sql}) WHERE ROWNUM <= {int(max_rows_per_chunk) + 1}"`
- [x] 3.2 在 `read_sql_df` 回傳後判斷：若 rows == max_rows_per_chunk + 1，log warning 並截斷為 `df.head(max_rows_per_chunk)`

## 4. Streaming Merge to Spool

- [x] 4.1 在 `batch_query_engine.py` 新增 `merge_chunks_to_spool()` 函式（在 `iterate_chunks()` 之後），接受 `cache_prefix, query_hash, spool_dir, max_total_rows, overflow_mode` 參數
- [x] 4.2 實作串流邏輯：以 `iterate_chunks()` 逐塊 yield → 轉 `pyarrow.Table` → 第一個 chunk 建立 `ParquetWriter` → 後續 chunk `write_table()` → 累計 total_rows 並檢查 max_total_rows
- [x] 4.3 處理邊界：空結果回傳 `(None, 0)`、異常時 finally 刪除部分 spool 檔案、overflow_mode="error" 時 raise `MergeChunksMaxRowsExceeded`
- [x] 4.4 修改 `reject_dataset_cache.py` 的 `execute_primary_query()`（line 722-728），將 `merge_chunks()` 呼叫替換為 `merge_chunks_to_spool()`
- [x] 4.5 確保 spool 結果註冊到現有 spool metadata store（Redis key + TTL），供 /view 和 /export-cached 端點讀取
- [x] 4.6 確保 `get_batch_progress()` 在 spool 寫入後、`redis_clear_batch()` 前被呼叫，partial failure metadata 正確傳遞

## 5. Gunicorn 設定調整

- [x] 5.1 修改 `.env` 中 `GUNICORN_MAX_REQUESTS=5000` 和 `GUNICORN_MAX_REQUESTS_JITTER=1000`

## 6. 測試與驗證

- [x] 6.1 新增/更新 `test_batch_query_engine.py`：測試 `merge_chunks_to_spool()` 的正常流程、空結果、超限 raise、spool 檔案清理
- [x] 6.2 新增測試：rate limit 裝飾器在第 11 次請求回 429
- [x] 6.3 新增測試：RSS guard 在 `process_rss_mb()` 回傳 950 時回 503 SERVICE_OVERLOADED
- [x] 6.4 新增測試：SQL ROWNUM 包裹邏輯（mock `read_sql_df` 驗證 SQL 字串含 `ROWNUM`）
- [x] 6.5 執行全量 pytest 確認無回歸
