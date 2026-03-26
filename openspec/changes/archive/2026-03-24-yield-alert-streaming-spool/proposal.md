## Why

2026-03-24 的 Worker 記憶體監控圖表顯示：memory guard 砍掉 worker 後，重啟的 worker RSS 在 10 分鐘內從 200MB 爬回 900MB，系統記憶體持續維持在 90.8%，eviction 每分鐘觸發但無效。

根因是 `yield_alert_dataset_cache.execute_primary_query` 使用 `read_sql_df_slow` 一次將 662K rows 載入 pandas DataFrame（~200MB），接著在 normalize、spool write、Redis store 過程中被完整 materialize 4 次，峰值可達 600MB。兩個 worker 的 warmup 無 distributed lock，同時查 Oracle 導致系統 peak 400-600MB。即使 `del df + gc.collect()`，glibc malloc arena fragmentation 也不還記憶體給 OS。

同時，`execute_linkage_query` 為了取 workorder 清單，會從 Redis 載入完整 662K rows detail_df 回 process memory（又一次 ~200MB peak）。

現有 DuckDB + spool parquet 架構已能處理 view 計算（out-of-core），但 primary query 和 linkage query 仍走 pandas 全量載入，是記憶體瓶頸的根源。

此外，現行 `yield-alert-spool-query` 規格仍假設「spool 失敗可回退 Redis detail_df」，但本提案要移除 Redis L2 detail，若不補齊 fail policy、空結果快取語意與 metadata 策略，會出現規格與實作矛盾。

## What Changes

將 yield_alert_dataset_cache 的 primary query 改為 streaming write pipeline，消除 662K rows DataFrame 進入 process memory 的路徑。依據資料特性分層存儲：大數據走 spool parquet + DuckDB，小數據留 Redis。

1. **Streaming primary query**：`read_sql_df_slow` → `read_sql_df_slow_iter`（fetchmany 5000）→ 逐 chunk normalize → `ParquetWriter` 直寫 spool → `register_spool_file`。Peak memory 從 ~600MB 降至 ~5MB。

2. **移除 Redis L2 detail_df**：不再 `redis_store_df(detail_df)`。662K rows 的 5.7MB parquet 只存 disk spool，由 DuckDB 直讀。省 ~8MB Redis 記憶體。

3. **保留 Redis linkage_df**：linkage_df 僅 ~20KB、跨 worker 共享、計算成本高（Oracle reject history query），適合留在 Redis。

4. **Linkage query 改走 DuckDB**：`SELECT DISTINCT WORKORDER FROM read_parquet(spool)` 取代 `_load_detail_df_from_redis`（662K rows）。記憶體從 ~200MB 降至 ~1MB。

5. **Pandas fallback data source 改為 spool**：`pd.read_parquet(spool_file)` 取代 `redis_load_df`。Fallback 仍存在但 data source 從 Redis 改為 disk。

6. **Warmup distributed lock**：`_warmup_yield_alert_dataset` 加 `try_acquire_lock`，防止多 worker 同時查 Oracle。

7. **query_id single-flight lock**：`execute_primary_query` 加 query_id 級 distributed lock，避免同條件 client 並發查詢在多 worker 重複打 Oracle。

8. **空結果快取 marker + 日期 metadata**：對 0 rows 查詢仍建立 lightweight cache marker（`empty_result=true`）並持久化 `start_date/end_date`；避免 0 rows 每次重查，並供 linkage/query 行為一致。

9. **明確 spool 失敗策略（移除 Redis detail 後）**：若 streaming 寫檔/註冊 spool 失敗，主查詢 SHALL 回傳 retryable overload（503 + Retry-After + machine-readable code），不發布不可用的 query marker。

10. **Rollout/rollback 開關與可觀測性**：新增 feature flag（建議 `YIELD_ALERT_STREAMING_SPOOL_ENABLED`）控制新舊路徑切換，並補齊 spool/register 失敗、single-flight 命中、empty-result hit 的觀測欄位。

## Capabilities

### Modified Capabilities
- `yield-alert-center-api`：primary query pipeline 改為 streaming write；linkage query 改用 DuckDB 取 workorder 清單；移除 Redis L2 detail 存儲。API contract 不變。
- `yield-alert-spool-query`：spool 失敗語意、空結果快取、data source tiering（Redis linkage only + spool detail）規格同步更新。

## Scope

### In Scope
- `yield_alert_dataset_cache.py`：streaming write、Redis L2 detail 移除、linkage DuckDB 化、pandas fallback source 切換
- `cache_updater.py`：warmup distributed lock
- `yield-alert-spool-query/spec.md` + `yield-alert-center-api/spec.md`：spec delta 同步（spool fail policy、empty-result marker、single-flight）
- 相關 telemetry/log 欄位（spool/register 失敗、single-flight wait/hit、empty-result cache hit）
- 相關測試更新

### Out of Scope
- `yield_alert_sql_runtime.py`（DuckDB view 路徑，不需修改）
- `query_spool_store.py`（`register_spool_file` 已存在，不需修改）
- `database.py`（`read_sql_df_slow_iter` 已存在，不需修改）
- 其他 dataset cache（reject、hold、resource）——各自的 streaming 改造留待後續
- 完全移除 pandas fallback path（保留作為 safety net）
- 前端改動（response format 不變）
