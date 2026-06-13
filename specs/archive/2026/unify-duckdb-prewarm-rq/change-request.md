# Change Request

## Original Request

兩個頁面（設備歷史績效 resource-history、設備停機分析 downtime-analysis）的 DuckDB prewarm 目前用 daemon thread 啟動，要統一改成走 RQ（與其他重查詢一致）。
啟動時跑三個月 prewarm，之後每日一次刷新（DuckDB keyed by `loaded_at == today`）。
Downtime analysis 補上 RQ spool warmup（目前沒有）。
Spool TTL 從 2h 改為 20h（略短於一天，確保每日 DuckDB 刷新後下一個查詢讀到新資料）。

## Business / User Goal

所有重查詢快取統一由 RQ 管理，可透過 RQ dashboard 監控、retry；消除 daemon thread 無法觀察的問題。
Spool TTL 對齊 DuckDB 每日刷新週期，避免在資料未更新的情況下每 2h 無意義重建 parquet。

## Non-goals

- 不改變 DuckDB 刷新頻率（維持每日一次）
- 不改變三個月快取窗口大小
- 不改變 Oracle 分段批次查詢邏輯（超出三個月的查詢路徑不動）
- 不改變其他 dataset（hold、reject、yield_alert）的 TTL

## Constraints

- RQ worker 必須在 gunicorn 啟動前或同時存在，否則首次查詢走 Oracle fallback（可接受）
- `CACHE_TTL_DATASET` 全域常數不能動（影響其他服務）；TTL 修改必須限定在 resource_history / downtime_analysis 兩個 service
- DuckDB 檔案路徑繼續從 env var 讀取，不寫死絕對路徑（Docker 相容）
- 不能 commit `.env`

## Known Context

- resource_history_duckdb_cache.py：daemon thread + fcntl file lock + `loaded_at == today` 判斷
- downtime_analysis_duckdb_cache.py：同樣 daemon thread，但 spool warmup 未加入 _WARMUP_JOBS
- spool_warmup_scheduler.py：WARMUP_INTERVAL_SECONDS=3600，leader lock via Redis，_WARMUP_JOBS 有 reject/yield_alert/hold/resource_dataset
- store_spooled_df：Redis 只存 metadata（JSON pointer），parquet 存磁碟；TTL 到期 metadata 消失，parquet 仍在
- app.py 目前在啟動時直接呼叫兩個 start_duckdb_prewarm()

## Open Questions

（無）

## Requested Delivery Date / Priority

盡快，中等優先
