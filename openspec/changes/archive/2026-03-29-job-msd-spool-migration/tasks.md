## 1. job_query_service spool 遷移

- [x] 1.1 在 `job_query_service.py` engine path 將 `merge_chunks()` 替換為 `merge_chunks_to_spool()`，寫入 spool namespace `"job_query"`，並呼叫 `register_spool_file()` 註冊
- [x] 1.2 移除 engine path 的 `redis_store_df(cache_key, df)` 呼叫
- [x] 1.3 將 engine path 結果讀取從 `df.iterrows()` 改為 DuckDB `read_parquet()` → records 轉換，保持回傳格式（datetime 格式化、None 處理）與現有一致
- [x] 1.4 調整 Redis cache-hit 路徑：改為先檢查 spool metadata（`get_spool_metadata` 或 `get_spool_file_path`），命中時用 DuckDB 讀取；移除 `redis_load_df` 呼叫

## 2. mid_section_defect_service spool 遷移

- [x] 2.1 在 `_fetch_station_detection()` engine path 將 `merge_chunks()` 替換為 `merge_chunks_to_spool()`，寫入 spool namespace `"msd_detect"`，並呼叫 `register_spool_file()` 註冊
- [x] 2.2 engine path 結果改為從 spool parquet 以 DuckDB 讀出 DataFrame 或 records，保持回傳介面不變（回傳 DataFrame 給呼叫方）
- [x] 2.3 確認 `cache_set(cache_key, df.to_dict('records'))` 在 engine path 的處理方式——若結果已在 spool 則不需再存 Redis records cache

## 3. 共用輔助

- [x] 3.1 建立 spool → records 的 DuckDB 讀取輔助函式（若 `query_spool_store` 尚無此功能），處理 datetime 格式化與 null 值轉換，供 job_query 和 msd_detect 共用
- [x] 3.2 確認 spool TTL 設定與原 Redis cache TTL 對齊（job_query: `_JOB_CACHE_TTL`、msd_detect: `CACHE_TTL_DETECTION`）

## 4. 測試

- [x] 4.1 為 job_query engine path 新增/更新測試：驗證 `merge_chunks_to_spool` 被呼叫、spool 註冊成功、回傳格式正確
- [x] 4.2 為 msd_detect engine path 新增/更新測試：驗證 spool 寫入、回傳 DataFrame 格式不變
- [x] 4.3 執行既有 job_query 和 mid_section_defect 測試，確認無 regression
