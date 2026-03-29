## Why

目前 reject/hold/resource/yield-alert 四個歷史域在每次查詢後會將完整 DataFrame 序列化（Parquet+base64）存入 Redis，單次可佔 5–100 MB，Redis peak 估計 200–400 MB。這與已完成的 production-history、material-trace、MSD 模式衝突——後者只存 spool 路徑 metadata（< 1 KB），本體留在 spool 檔。Phase 2 目標是讓這四個域對齊 metadata-only 模型，消除 Redis 中的大型 payload，預計 Redis peak 降至 50–100 MB。

## What Changes

- **reject-dataset-cache**：停止呼叫 `redis_store_df()`（`reject_dataset:` namespace）；改在 spool 寫完後呼叫 `query_spool_store.register_spool_file()` 注冊 metadata pointer
- **hold-dataset-cache**：同上，停止 `redis_store_df()`（`hold_dataset:` namespace）；走 `query_spool_store` metadata path
- **resource-dataset-cache**：同上，停止 `redis_store_df()`（`resource_dataset:` namespace）
- **yield-alert-dataset-cache**：yield-alert 的 linkage_df（cross-worker lot→alert 對照）目前走 `redis_store_df()` 存 Redis；改為只存 spool metadata（linkage 本身是一個 Parquet spool），移除 base64 Redis payload
- **redis_df_store.py**（共用層）：`redis_store_df` / `redis_load_df` 保留，供 batch-query chunk（小塊，非 large payload）使用；標記四個域已不再使用此函式
- **相容性 fallback**：新路徑預設啟用；舊 `redis_load_df` 讀取路徑保留為 feature flag（`PHASE2_METADATA_ONLY=0` 回退）供平行驗證
- **BREAKING**：`reject_dataset_cache._load_df_on_demand()` / `hold_dataset_cache._load_df_on_demand()` / `resource_dataset_cache._load_df_on_demand()` 內部行為改變（Redis miss → spool metadata 查找），外部 API contract 不變

## Capabilities

### New Capabilities

- `dataset-cache-metadata-only-redis`: 四個重查詢域的 Redis 儲存策略從 DataFrame payload 改為 spool metadata pointer，定義統一 metadata 結構與 feature flag 切換機制

### Modified Capabilities

- `resource-dataset-cache`: L2 Redis 儲存策略由 Parquet+base64 改為 spool metadata pointer；`_store_to_cache()` / `_load_df_on_demand()` 行為變更
- `hold-dataset-cache`: 同上，適用於 hold 域
- `reject-history-api`: reject 域 L2 cache 寫入路徑變更（`_write_cache_new_path()` 不再呼叫 `redis_store_df`）
- `yield-alert-spool-query`: linkage_df 改用 spool metadata 儲存，移除 `redis_store_df(linkage_key, linkage_df)`

## Impact

- **後端服務**：`reject_dataset_cache.py`, `hold_dataset_cache.py`, `resource_dataset_cache.py`, `yield_alert_dataset_cache.py`, `redis_df_store.py`
- **共用基礎設施**：`query_spool_store.py`（已有 `register_spool_file()` 可重用）
- **Redis namespace 消除**：`reject_dataset:`, `hold_dataset:`, `resource_dataset:`, `yield_alert:*linkage*` 這四個 namespace 的大型 payload key 將不再寫入
- **Redis namespace 保留**：`batch_query:chunk:*`（小塊）繼續使用 `redis_df_store`
- **feature flag**：新增環境變數 `PHASE2_METADATA_ONLY`（預設 `1`），設為 `0` 可回退至舊路徑
- **不影響**：前端 API contract、spool 檔案格式、DuckDB view engine、TTL 設定（spool TTL 維持 900s）
