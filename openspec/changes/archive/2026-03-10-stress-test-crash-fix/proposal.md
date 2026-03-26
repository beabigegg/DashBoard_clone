## Why

2026-03-10 壓測期間，大量併發 `POST /api/reject-history/query` 導致 worker OOM 崩潰。根因是 `merge_chunks()` 全量載入所有 chunk DataFrame 後 `pd.concat()`，峰值記憶體約為資料量 2 倍。同時 `/query` 端點缺少 rate limit 與 RSS 前置檢查，高壓下 RSS 飆升連帶影響 trace/query-tool 端點（共用 1100MB 閾值），形成跨端點級聯故障。需在不遺失資料前提下改善系統穩定性。

## What Changes

- 為 `POST /api/reject-history/query` 加入 rate limit（10/60s），與 /list、/export 對齊
- 在 reject 查詢執行前加 RSS 前置檢查（900MB 閾值），比 trace/query-tool 的 1100MB 更早攔截
- 在 `_run_reject_chunk()` 中以 `ROWNUM` 強制執行 `max_rows_per_chunk`，取代僅 log 的假實作
- 新增 `merge_chunks_to_spool()` 串流合併函式，利用現有 `iterate_chunks()` 逐塊寫入 parquet，峰值記憶體降至單 chunk 等級
- 調高 `GUNICORN_MAX_REQUESTS` 至 5000（worker 回收改由 RSS guard 主導）

## Capabilities

### New Capabilities
- `reject-query-backpressure`: Rate limit、RSS 前置檢查、SQL 層 per-chunk 行數限制 — 對 reject-history /query 端點的入口背壓機制
- `streaming-chunk-merge`: 基於 iterate_chunks + ParquetWriter 的串流合併路徑，替代全量 merge_chunks

### Modified Capabilities
- `batch-query-resilience`: merge 路徑改為串流 spool，需確保 partial-failure metadata 語義不變
- `reject-history-api`: /query 端點加裝 rate limit decorator

## Impact

- **後端路由**: `reject_history_routes.py` — 新增 rate limit decorator
- **服務層**: `reject_dataset_cache.py` — RSS guard、SQL ROWNUM、改用 spool merge
- **引擎層**: `batch_query_engine.py` — 新增 `merge_chunks_to_spool()` 函式
- **設定**: `.env` — rate limit 參數、RSS 閾值、max_requests 調整
- **相依**: pyarrow（已存在於 requirements）
- **無 breaking change**: 原有 `merge_chunks()` 保留不動，僅 reject 路徑切換
