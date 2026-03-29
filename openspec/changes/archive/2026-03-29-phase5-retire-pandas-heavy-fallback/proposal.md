## Why

Phase 3 已將四個重查詢域（resource / hold / yield-alert / reject）的 `apply_view()` 全面切換至 DuckDB SQL runtime，pandas fallback 已移除。但 `execute_primary_query()` 的 Oracle cold-start 路徑仍保留完整的 pandas `_derive_*()` 衍生邏輯與 `_get_cached_df()` Redis DataFrame 讀寫，這是目前最大的 RAM spike 來源。Phase 4 已正式定義 Type A / Type B 語意契約，確認各域的 410 re-query 行為正確，現在可以安全地移除 pandas heavy path。

## What Changes

- **移除** `resource_dataset_cache.py` 中 `execute_primary_query()` 的 pandas `_derive_*()` 衍生路徑：`_derive_summary()`, `_derive_kpi()`, `_derive_trend()`, `_derive_heatmap()`, `_derive_comparison()`, `_derive_detail()`, `_get_cached_df()`
- **移除** `hold_dataset_cache.py` 中 `execute_primary_query()` 的 pandas `_derive_all_views()` 衍生路徑：`_derive_trend()`, `_derive_reason_pareto()`, `_derive_duration()`, `_derive_list()`, `_get_cached_df()`
- **移除** `yield_alert_dataset_cache.py` 中 `execute_primary_query()` 內的 pandas 衍生函式（`_build_summary_and_trend()`, `_build_heatmap_data()`, `_build_station_summary()`, `_build_package_summary()`, `_build_alerts_view()` 等），改為只負責 Oracle → spool 落盤 + 回傳 query_id
- **移除** `reject_dataset_cache.py` 中 `_build_primary_response()` 的 pandas `_derive_analytics_raw()`, `_derive_summary_from_analytics()`, `_derive_trend_from_analytics()` 衍生路徑，以及 batch pareto / export 中殘留的 `_allow_legacy_fallback()` gate
- **重構** `execute_primary_query()` 回傳模式：spool 落盤後直接呼叫 DuckDB SQL runtime 的 `apply_view()` 取得 computed result，不再以 pandas 衍生結果作為 primary response
- **移除** Redis 大型 DataFrame 寫入（`_get_cached_df` / `_dataset_cache.set` 對 full DataFrame 的存取）；保留 metadata-only marker

## Capabilities

### New Capabilities

（無新增 capability）

### Modified Capabilities

- `resource-dataset-cache`: 移除 `execute_primary_query()` pandas 衍生路徑，改為 spool → DuckDB 回傳
- `hold-dataset-cache`: 移除 `execute_primary_query()` pandas 衍生路徑，改為 spool → DuckDB 回傳
- `yield-alert-spool-query`: 移除 `execute_primary_query()` pandas 衍生路徑，改為 spool → DuckDB 回傳
- `reject-history-api`: 移除 `_build_primary_response()` pandas 衍生路徑與殘留 legacy fallback gate

## Impact

- **RAM**：移除 Oracle cold-start 後的 pandas DataFrame 衍生，消除最大 RAM spike 來源
- **API response**：`execute_primary_query()` 回傳結構不變（同樣包含 summary / detail / kpi 等），但資料來源從 pandas 切換為 DuckDB
- **Redis**：不再寫入大型 DataFrame，僅保留 metadata marker、job status、filter cache
- **風險**：pandas 衍生結果與 DuckDB 結果可能有微小數值差異（浮點精度、排序穩定性），需回歸測試確認
- **受影響檔案**：`services/resource_dataset_cache.py`, `services/hold_dataset_cache.py`, `services/yield_alert_dataset_cache.py`, `services/reject_dataset_cache.py`，以及對應的測試檔案
