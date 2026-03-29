## Why

`job_query_service` 和 `mid_section_defect_service` 的長日期範圍查詢仍使用 `merge_chunks()` 將所有 Redis chunk 重組成完整 pandas DataFrame，再以 `redis_store_df()` 回存。這導致 RAM 尖峰為結果集大小的 2 倍（merge + pickle 序列化）。同樣的模式在 `production_history`、`hold_dataset_cache`、`resource_dataset_cache`、`reject_dataset_cache` 已成功遷移到 `merge_chunks_to_spool()` + DuckDB page/export，這兩個 domain 是最後未遷移的。

## What Changes

- **job_query_service**：長日期範圍的 engine path 從 `merge_chunks()` → `redis_store_df()` 改為 `merge_chunks_to_spool()` → `register_spool_file()` → DuckDB page/export
- **mid_section_defect_service**：station_detection engine path 同樣從 `merge_chunks()` 改為 `merge_chunks_to_spool()` → spool-based 回傳
- 兩個 domain 的路由層需配合調整，改用 spool metadata + DuckDB 查詢取代直接回傳 DataFrame 轉 JSON
- 移除遷移後不再需要的 `redis_store_df` / `redis_load_df` 呼叫點

## Capabilities

### New Capabilities

（無新增能力，本次為既有 spool pipeline 的延伸覆蓋）

### Modified Capabilities

- `unified-spool-pipeline`: 將 job_query 和 msd_detect 納入 spool pipeline 覆蓋範圍
- `streaming-chunk-merge`: job_query 和 msd_detect 改用 `merge_chunks_to_spool()` 取代 `merge_chunks()`

## Impact

- **後端服務**：`job_query_service.py`、`mid_section_defect_service.py`、對應 routes
- **RAM**：消除兩個 domain 在長日期範圍查詢時的完整 DataFrame 記憶體尖峰
- **Redis**：減少大型 merged DataFrame 的 Redis 儲存壓力
- **API 行為**：回傳格式不變（JSON），但內部從 pandas → DuckDB 讀取 parquet spool
- **無破壞性變更**：前端不需修改
