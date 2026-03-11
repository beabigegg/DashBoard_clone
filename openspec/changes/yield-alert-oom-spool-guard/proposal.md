## Why

Yield Alert Center 的 `apply_view` 在處理 30 天 ERP WIP 資料時造成 Gunicorn worker OOM crash。根因是此模組完全缺乏其他重查詢模組（reject-history、trace、query-tool）已有的記憶體保護（interactive memory guard），且每次 view 請求都將完整 DataFrame 載入 pandas 做聚合，同時產生多份副本導致峰值記憶體暴增 5-7 倍。

## What Changes

- 在 `execute_primary_query` 和 `apply_view` 加入 `enforce_dataset_memory_guard` 兩道柵欄保護，拒絕時回傳 503 + 明確訊息（非靜默失敗）
- 在 route 層捕獲 `MemoryError` 回傳 `SERVICE_UNAVAILABLE` 503 回應
- 將 primary query 結果寫入 parquet spool 磁碟快取（複用 `query_spool_store`）
- 新建 `yield_alert_sql_runtime.py`，以 DuckDB 直接查詢 parquet 檔案完成 view 聚合（summary / trend / heatmap / station_summary / package_summary / alerts 分頁），不需將完整 DataFrame 載入記憶體
- `apply_view` 改為 DuckDB-first + pandas fallback 架構
- 消除 `_build_heatmap_data` 中不必要的 `.copy()` 呼叫
- 優化 `_build_alerts_view` 將全量具現化改為向量化計算 + pandas 內分頁
- 降低 `_CACHE_MAX_SIZE` 預設值 6 → 3

## Capabilities

### New Capabilities
- `yield-alert-spool-query`: Yield Alert 的 parquet spool 寫入 + DuckDB SQL runtime out-of-core 查詢能力

### Modified Capabilities
- `yield-alert-center-api`: 加入 interactive memory guard 保護與 MemoryError → 503 處理，apply_view 改為 DuckDB-first 架構

## Impact

- **後端檔案**：`yield_alert_dataset_cache.py`（memory guard + spool + DuckDB 整合 + pandas 優化）、`yield_alert_routes.py`（MemoryError 捕獲）
- **新增檔案**：`yield_alert_sql_runtime.py`（DuckDB SQL runtime）
- **依賴**：複用既有 `core/interactive_memory_guard.py`、`core/query_spool_store.py`、`core/feature_flags.py`；DuckDB 已在 `requirements.txt`
- **前端**：無變更（API 契約不變，僅後端執行路徑改變）
- **可觀測性**：memory guard 拒絕時會記錄 log（RSS/df_mb/projected），DuckDB 路徑記錄查詢延遲
