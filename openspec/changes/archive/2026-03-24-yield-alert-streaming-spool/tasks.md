## Phase 1: Streaming write pipeline

- [x] 1.1 新增 `_prepare_detail_chunk(columns, rows)` 函式：接收 `read_sql_df_slow_iter` yield 的 `(columns, rows)` tuple，建構 mini DataFrame 並 in-place normalize（欄位對齊 `_DETAIL_COLUMNS`），回傳 `pa.Table`
- [x] 1.2 新增 `_streaming_write_to_spool(sql, params, query_id)` 函式：呼叫 `read_sql_df_slow_iter` → 逐 chunk `_prepare_detail_chunk` → `ParquetWriter.write_table` → `register_spool_file`，回傳 `(spool_path, total_rows)`。處理空結果和 schema 對齊
- [x] 1.3 重寫 `execute_primary_query`：移除 `read_sql_df_slow` + `_prepare_detail_df` + `store_spooled_df` + `redis_store_df(detail_df)` 路徑，改呼叫 `_streaming_write_to_spool`。L1 只存 `{ "linkage_df": empty, "spool_ready": True }`
- [x] 1.4 加入 feature flag（建議 `YIELD_ALERT_STREAMING_SPOOL_ENABLED`）切換 streaming/new path 與 legacy path，支援 rollout/rollback
- [x] 1.5 加入 query_id 級 single-flight distributed lock（acquire/wait/retryable timeout）避免同條件並發重查 Oracle

## Phase 2: 移除 Redis L2 detail，簡化 cache 層

- [x] 2.1 移除 `_store_payload` 中的 `redis_store_df(_detail_cache_key(...), detail_df)` 呼叫（保留 linkage_df 的 Redis 存儲）
- [x] 2.2 移除 `_load_detail_df_from_redis`、`_detail_cache_key`、`_redis_key_exists`（detail 用途）函式
- [x] 2.3 重寫 `_get_cached_payload`：L1 hit 判斷改為 payload marker 存在 + `get_spool_file_path` 非 None；Redis fallback 只載入 linkage_df（不再檢查 detail key existence）
- [x] 2.4 簡化 `_store_payload` 簽名：不再接收 `detail_df` 參數，只存 `linkage_df` 到 Redis + L1 marker
- [x] 2.5 新增 empty-result cache marker（`empty_result=true`, `spool_ready=false`）以避免 0 rows 查詢反覆重查
- [x] 2.6 持久化 query date metadata（`start_date`,`end_date`）供 linkage 與 fallback 路徑使用

## Phase 3: Linkage query DuckDB 化

- [x] 3.1 新增 `_extract_workorders_from_spool(query_id)` 函式：用 DuckDB `SELECT DISTINCT "WORKORDER" FROM read_parquet(spool_path)` 取 workorder 清單，回傳 `list[str]`
- [x] 3.2 重寫 `execute_linkage_query`：以 `_extract_workorders_from_spool` 取代 `_load_detail_df_from_redis` → extract workorders 路徑。spool miss 時直接返回 linkage_not_ready。Oracle reject linkage query 不變
- [x] 3.3 linkage 查詢日期來源改用 metadata（非 detail_df min/max）

## Phase 4: Pandas fallback source 切換

- [x] 4.1 新增 `_load_detail_df_from_spool(query_id)` 函式：`pd.read_parquet(get_spool_file_path(namespace, query_id))` 取代原有的 Redis 載入
- [x] 4.2 `apply_view` pandas fallback path：將 `_load_detail_df_from_redis(query_id)` 替換為 `_load_detail_df_from_spool(query_id)`
- [x] 4.3 `_compute_filter_options` 在 pandas fallback 中改用 `detail_df`（from spool）而非 `payload["detail_df"]`（已為 None）
- [x] 4.4 明確處理 empty-result marker：DuckDB/pandas 路徑都回傳空成功結果（非 cache miss）

## Phase 5: Spool 失敗契約與 warmup lock

- [x] 5.1 streaming 寫檔或 register 失敗時，主查詢回傳 `503 SERVICE_UNAVAILABLE` + `Retry-After` + machine-readable code（不發布不可用 query marker）
- [x] 5.2 `cache_updater._warmup_yield_alert_dataset` 加 `try_acquire_lock("yield_alert_warmup", ttl_seconds=120)` + `release_lock` 保護

## Phase 6: 可觀測性、清理與測試

- [x] 6.1 移除 `yield_alert_dataset_cache.py` 中不再使用的 import（`REDIS_ENABLED`、`get_redis_client`）
- [x] 6.2 更新現有測試：mock/patch 調整（`_load_detail_df_from_redis` → `_load_detail_df_from_spool`，移除 Redis detail 相關 assertion）
- [x] 6.3 新增 streaming write 單元測試：驗證 `_prepare_detail_chunk` 產出 schema 與 `_DETAIL_COLUMNS` 一致
- [x] 6.4 新增整合測試：verify primary query → spool → DuckDB view → response 全路徑正確性
- [x] 6.5 新增 telemetry/log 欄位與驗證（spool/register fail、single-flight wait/hit、empty-result cache hit、fallback reason）
- [x] 6.6 新增故障模式測試：spool register fail、single-flight contention、empty-result cache hit、metadata 缺失 fallback

## Phase 7: OpenSpec 規格同步

- [x] 7.1 更新 `openspec/specs/yield-alert-center-api/spec.md` delta（streaming write、Redis L2 detail 移除、retryable overload）
- [x] 7.2 更新 `openspec/specs/yield-alert-spool-query/spec.md` delta（移除 Redis detail fallback 假設、補 empty-result/single-flight/spool-fail 契約）
