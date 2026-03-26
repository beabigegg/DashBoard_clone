## Context

`yield_alert_dataset_cache.execute_primary_query` 是目前 worker 記憶體爬升的最大單一來源。它使用 `read_sql_df_slow` 一次載入 662K rows（~200MB DataFrame），在 normalize/spool/Redis store 過程中被 materialize 4 次，峰值可達 600MB。重啟後兩個 worker 同時 warmup 更是加倍。

其他 dataset cache（reject）已採用 `batch_query_engine` + `merge_chunks_to_spool` 的 streaming pipeline，但 yield_alert 因為不需要 time-range decomposition，仍使用舊的全量載入模式。

現有 DuckDB view 路徑（`yield_alert_sql_runtime.py`）已完整實作 summary/trend/heatmap/station/package/alerts/filter_options，且 parquet spool file 僅 5.7MB（Parquet columnar 壓縮後），DuckDB 從 disk 讀取 + 聚合僅需 0.5-0.8s。

## Goals / Non-Goals

**Goals**
- 消除 primary query 中 662K rows DataFrame 進入 process memory 的路徑
- 依資料大小/熱度分層存儲：大數據（detail）走 spool + DuckDB，小數據（linkage）留 Redis
- 保持所有 API response format 不變
- 保留 pandas fallback path 作為 safety net（data source 從 Redis 改為 spool parquet）
- 明確定義 spool/register 失敗時的 retryable 行為（避免回傳不可用 query_id）
- 讓 0 rows 查詢可被快取命中（避免空結果反覆重查 Oracle）

**Non-Goals**
- 不改變 DuckDB view 路徑（已經 OK）
- 不改變 anomaly detection scheduler（只複製 spool file，不受影響）
- 不完全移除 pandas fallback（風險太大）
- 不改其他 dataset cache（reject/hold/resource 的 streaming 改造留待後續）

## Decisions

### D1. Streaming write 使用 `read_sql_df_slow_iter` + PyArrow `ParquetWriter`

- **Decision**: 不走 `batch_query_engine`，而是直接使用 `read_sql_df_slow_iter`（fetchmany 5000）+ `ParquetWriter` 逐 chunk 寫入 spool。
- **Rationale**: yield_alert 的 SQL 是單一 GROUP BY 查詢，不需要 time-range decomposition 或 ID-batch decomposition。直接 streaming 比繞道 batch_query_engine（Redis chunk 中繼）更簡單、更省記憶體。
- **Reference**: `batch_query_engine.merge_chunks_to_spool` 的 `ParquetWriter` 模式可作為 pattern 參考。

### D2. `_prepare_detail_df` 改為 chunk-level in-place normalize

- **Decision**: 新增 `_prepare_detail_chunk(columns, rows)` 函式，接收 `read_sql_df_slow_iter` yield 的 `(columns, rows)` tuple，建構 mini DataFrame 並 in-place normalize（不 `.copy()`），回傳 PyArrow Table。
- **Rationale**: 現有 `_prepare_detail_df` 先 `df.copy()` 再逐欄 normalize，一個 chunk（5000 rows）做 copy 可接受（~2MB），但避免不必要 copy 仍可省一半暫態記憶體。
- **Schema**: normalize 後的 column set 與現有 `_DETAIL_COLUMNS` 完全一致，確保 spool parquet schema 不變，DuckDB view 路徑零影響。

### D3. 移除 Redis L2 detail_df，保留 linkage_df

- **Decision**: `_store_payload` 不再呼叫 `redis_store_df(_detail_cache_key(query_id), detail_df)`。移除 `_detail_cache_key`、`_load_detail_df_from_redis`、`_redis_key_exists`（detail 用途）。保留 `redis_store_df(_linkage_cache_key(...), linkage_df)`。
- **Rationale**:
  - detail_df 5.7MB parquet（base64 後 ~8MB in Redis），TTL 300s，重啟後大概率 miss → 價值低、成本高
  - linkage_df ~20KB，跨 worker 共享，Oracle reject query 計算成本高 → 價值高、成本低
- **Data tiering**: 大+熱 → spool + DuckDB；小+熱+共享 → Redis + L1。

### D4. `_get_cached_payload` validity 改為 L1 + spool file 存在性

- **Decision**: cache hit 判斷改為：L1 payload marker 存在 AND spool file 存在（`get_spool_file_path` 非 None）。不再查 Redis detail key existence。
- **Rationale**: 移除 Redis L2 detail 後，spool file 是 detail data 的唯一 source of truth（TTL 6 小時 vs Redis 300s）。L1 的 linkage_df 仍從 Redis promote。

### D5. `execute_linkage_query` 用 DuckDB 取 workorder 清單

- **Decision**: 不再 `_load_detail_df_from_redis` 載入 662K rows，改為 `duckdb.connect(":memory:").execute("SELECT DISTINCT WORKORDER FROM read_parquet(?)")` 取 workorder 清單。之後的 Oracle reject linkage query 不變。
- **Rationale**: 只需要 distinct workorder list（通常數千個 string），不需要載入全部 662K rows 的所有欄位。DuckDB columnar scan 只讀 WORKORDER 一欄，記憶體 ~1MB。

### D6. Pandas fallback data source 從 Redis 改為 spool parquet

- **Decision**: `apply_view` 的 pandas fallback path 中，`_load_detail_df_from_redis(query_id)` 改為 `pd.read_parquet(get_spool_file_path(namespace, query_id))`。
- **Rationale**: 移除 Redis L2 detail 後，spool parquet 是唯一 data source。載入方式從 Redis GET + base64 decode + read_parquet 簡化為直接 read_parquet from disk。Fallback 仍載入全量 DataFrame（~200MB），但這只在 DuckDB fail 時才走。

### D7. Warmup distributed lock

- **Decision**: `cache_updater._warmup_yield_alert_dataset` 加 `try_acquire_lock("yield_alert_warmup", ttl_seconds=120)`，取得鎖才執行 `ensure_dataset_loaded`，否則 skip。
- **Rationale**: 同 `_check_and_update` 已有的模式。防止 2 個 worker 同時 warmup 時各自查 Oracle，峰值減半。加上 streaming write 後，即使查了也只佔 ~5MB，但 lock 仍是好的防禦層。

### D8. query_id 級 single-flight lock

- **Decision**: `execute_primary_query` 增加 query_id 級 distributed lock（non-blocking acquire + bounded wait）。同條件查詢若已有 owner 在跑，其他 worker 等待結果或回傳可重試 overload。
- **Rationale**: warmup lock 只能防啟動時並發，不能避免 client 同條件並發重查。single-flight 可直接砍掉重複 Oracle 查詢峰值。

### D9. 空結果快取 marker + query date metadata

- **Decision**: 當 streaming 結果為 0 rows 時，不建立 parquet spool，但建立 lightweight payload marker（`empty_result=true`）並持久化 query date metadata（`start_date`,`end_date`）。
- **Rationale**: 若 cache hit 條件僅看 spool exists，0 rows 會永久 miss 並反覆打 Oracle；加 marker 後可命中快取且行為可預期。

### D10. spool/register 失敗的主查詢契約

- **Decision**: 移除 Redis L2 detail 後，若 streaming parquet 寫檔或 `register_spool_file` 失敗，主查詢不再回傳可用 query marker；改回 `503 SERVICE_UNAVAILABLE` + `Retry-After` + machine-readable code。
- **Rationale**: 既然 detail 唯一 source 是 spool，就不能發布不可用 query_id。以 retryable overload 契約比「成功但 view 失敗」更一致。

### D11. Rollout/rollback feature flag

- **Decision**: 新增 feature flag（建議 `YIELD_ALERT_STREAMING_SPOOL_ENABLED`）控制是否啟用 streaming primary path；關閉時回退現行路徑。
- **Rationale**: 允許漸進上線、快速回退，降低一次性切換風險。

### D12. 規格同步與可觀測性

- **Decision**: 同步更新 `yield-alert-center-api` 與 `yield-alert-spool-query` 規格，並統一記錄 telemetry/log（spool/register fail、single-flight wait/hit、empty-result hit、fallback reason）。
- **Rationale**: 避免規格仍描述 Redis detail fallback（已不成立），並提升事故可診斷性。

## Component Interactions

```
execute_primary_query (改後):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  read_sql_df_slow_iter(sql, params)
       │ yield (columns, rows)  ×N batches
       ▼
  _prepare_detail_chunk(columns, rows)
       │ → mini DataFrame (5000 rows)
       │ → in-place normalize
       │ → pa.Table.from_pandas
       ▼
  ParquetWriter.write_table(table)
       │ del mini_df, del table
       ▼ (repeat until exhausted)
  ParquetWriter.close()
       │
       ▼
  register_spool_file(namespace, query_id, tmp_path, total_rows)
       │ success
       ▼
  L1 cache: { "linkage_df": empty, "spool_ready": True, "empty_result": False }
  metadata: {start_date, end_date}
  (不存 Redis detail)

  register/write 失敗
       │
       ▼
  回傳 retryable overload (503 + Retry-After)
  (不發布 query marker)

  total_rows == 0
       │
       ▼
  L1 cache: { "linkage_df": empty, "spool_ready": False, "empty_result": True }
  metadata: {start_date, end_date}
  (視為可命中 cache 的空資料)


execute_linkage_query (改後):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  get_spool_file_path(namespace, query_id)
       │
       ▼
  DuckDB: SELECT DISTINCT "WORKORDER" FROM read_parquet(spool_path)
       │ → workorder list (~數千 strings, ~100KB)
       ▼
  _compute_reject_linkage(start_date, end_date, workorders)
       │ → Oracle query (不變)
       ▼
  linkage_df (~20KB) → redis_store_df + L1 cache


apply_view (改後):
━━━━━━━━━━━━━━━━

  DuckDB path (不變, primary path):
    spool parquet → DuckDB SQL → result
    + _enrich_alerts_with_linkage(linkage_df from L1/Redis)

  Pandas fallback (data source 改):
    pd.read_parquet(spool_path)     ← 原: redis_load_df
    → pandas aggregation (不變)
```

## Risk Assessment

1. **Schema drift**: streaming normalize chunk 必須產出與現有 `_DETAIL_COLUMNS` 完全一致的 schema，否則 DuckDB view 會 fail。**Mitigation**: 第一個 chunk 確定 schema 後，後續 chunk 用 `pa.Table.cast(schema)` 對齊。

2. **Empty result set**: 如果 Oracle 回傳 0 rows，`ParquetWriter` 不會被初始化。**Mitigation**: 檢查 `total_rows == 0` 時直接返回空結果，不 register spool file。

3. **Spool file 不存在時的 linkage/view 失敗**: spool TTL 6h 過期或 file 被清理後，linkage 和 view 都會失敗。**Mitigation**: `_get_cached_payload` 會檢查 spool exists，miss 時返回 None → caller 觸發 re-query。這與現有 Redis miss 行為一致。

4. **Pandas fallback 仍載入全量**: 改為 spool source 後，fallback 仍是 ~200MB peak。**Mitigation**: DuckDB 已是 primary path 且穩定運行。Fallback 僅在 DuckDB import fail 或 runtime error 時觸發，概率極低。

5. **Single-flight lock 飢餓/等待超時**: 高併發時等待者可能超時。**Mitigation**: bounded wait + 明確 `SERVICE_UNAVAILABLE` retryable 回應，避免無限阻塞。

6. **規格漂移**: 若只改 `yield-alert-center-api` 不改 `yield-alert-spool-query`，會殘留舊 fallback 敘述。**Mitigation**: 兩份 spec 同步更新並加 migration 註記。
