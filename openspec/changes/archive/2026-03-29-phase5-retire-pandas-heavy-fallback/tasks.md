## 0. 前置確認：pandas 呼叫者 audit

- [x] 0.1 Grep `resource_dataset_cache.py`：確認 `_derive_summary()`, `_derive_kpi()`, `_derive_trend()`, `_derive_heatmap()`, `_derive_comparison()`, `_derive_detail()` 僅被 `execute_primary_query()` 呼叫
- [x] 0.2 Grep `resource_dataset_cache.py`：確認 `_get_cached_df()` 僅被 `execute_primary_query()` 呼叫
- [x] 0.3 Grep `hold_dataset_cache.py`：確認 `_derive_all_views()`, `_derive_trend()`, `_derive_reason_pareto()`, `_derive_duration()`, `_derive_list()` 僅被 `execute_primary_query()` 呼叫
- [x] 0.4 Grep `hold_dataset_cache.py`：確認 `_get_cached_df()` 僅被 `execute_primary_query()` 呼叫
- [x] 0.5 Grep `yield_alert_dataset_cache.py`：確認 `_build_summary_and_trend()`, `_build_heatmap_data()`, `_build_station_summary()`, `_build_package_summary()`, `_build_alerts_view()`, `_compute_filter_options()` 呼叫者清單
- [x] 0.6 Grep `reject_dataset_cache.py`：確認 `_build_primary_response()`, `_derive_analytics_raw()`, `_derive_summary_from_analytics()`, `_derive_trend_from_analytics()` 呼叫者清單
- [x] 0.7 Grep `reject_dataset_cache.py`：確認 `_allow_legacy_fallback()` 在 batch pareto (L2024) 和 export (L2181) 的殘留呼叫，以及對應 DuckDB 路徑是否已覆蓋
- [x] 0.8 確認各域 `apply_view()` 的回傳結構與 `execute_primary_query()` 目前回傳結構的對應關係

## 1. resource-dataset-cache：移除 pandas 衍生路徑

- [x] 1.1 重構 `execute_primary_query()`：spool 落盤後呼叫 `apply_view(query_id, granularity, resource_filter)` 取得 computed result
- [x] 1.2 移除 `execute_primary_query()` 中對 `_derive_summary()` / `_derive_detail()` 的呼叫
- [x] 1.3 移除 `execute_primary_query()` 中對 `_get_cached_df()` 的呼叫（cache hit 路徑改走 `apply_view()`）
- [x] 1.4 刪除 `_derive_summary()`, `_derive_kpi()`, `_derive_trend()`, `_derive_heatmap()`, `_derive_comparison()`, `_derive_detail()` 函式定義（audit 確認零呼叫者後）
- [x] 1.5 刪除 `_get_cached_df()` 函式定義
- [x] 1.6 移除 Redis 大型 DataFrame 寫入（`redis_df_store` 相關呼叫），保留 `_dataset_cache.set(query_id, True)` metadata marker
- [x] 1.7 更新 `tests/test_resource_dataset_cache.py`：移除 pandas mock，改為驗證 DuckDB path
- [x] 1.8 執行 `pytest tests/test_resource_dataset_cache.py -v` 確認通過

## 2. hold-dataset-cache：移除 pandas 衍生路徑

- [x] 2.1 重構 `execute_primary_query()`：spool 落盤後呼叫 `apply_view(query_id)` 取得 computed result
- [x] 2.2 移除 `execute_primary_query()` 中對 `_derive_all_views()` 的呼叫
- [x] 2.3 移除 `execute_primary_query()` 中對 `_get_cached_df()` 的呼叫（cache hit 路徑改走 `apply_view()`）
- [x] 2.4 刪除 `_derive_all_views()`, `_derive_trend()`, `_derive_reason_pareto()`, `_derive_duration()`, `_derive_list()` 函式定義
- [x] 2.5 刪除 `_get_cached_df()` 函式定義
- [x] 2.6 移除 Redis 大型 DataFrame 寫入，保留 metadata marker
- [x] 2.7 更新 `tests/test_hold_dataset_cache.py`：移除 pandas mock，改為驗證 DuckDB path
- [x] 2.8 執行 `pytest tests/test_hold_dataset_cache.py -v` 確認通過

## 3. yield-alert-spool-query：移除 pandas 衍生路徑

- [x] 3.1 重構 `execute_primary_query()`：spool 落盤後只回傳 `query_id` + metadata，不做 pandas view 計算
- [x] 3.2 確認 route 層在收到 `execute_primary_query()` 回傳後呼叫 `apply_view()` 取得完整 view result
- [x] 3.3 移除 `execute_primary_query()` 中對 `_build_summary_and_trend()`, `_build_heatmap_data()`, `_build_station_summary()`, `_build_package_summary()`, `_build_alerts_view()`, `_compute_filter_options()` 的呼叫
- [x] 3.4 刪除 pandas helper 函式（audit 確認零呼叫者後）：`_build_summary_and_trend()`, `_build_heatmap_data()`, `_build_station_summary()`, `_build_package_summary()`, `_build_alerts_view()`, `_compute_filter_options()`
- [x] 3.5 評估 `_dedup_tx_df()`, `_bucket_date_str()`, `_vectorized_bucket()`, `_apply_dimension_filters()`, `_apply_reason_policy()`, `_to_numeric()` 是否仍有呼叫者，無則刪除
- [x] 3.6 更新 `tests/test_yield_alert_dataset_cache.py`：移除 pandas mock，改為驗證 DuckDB path
- [x] 3.7 執行 `pytest tests/test_yield_alert_dataset_cache.py -v` 確認通過

## 4. reject-history-api：移除 pandas 衍生路徑與 legacy fallback

- [x] 4.1 重構 `execute_primary_query()`：移除 `_build_response_from_cache()` pandas path，cache hit / spool write 後統一走 `apply_view()`
- [x] 4.2 移除 `_build_primary_response()` 呼叫，改用 `apply_view()` 回傳結果組裝 response
- [x] 4.3 移除 `_get_cached_df()` 呼叫與函式定義
- [x] 4.4 刪除 `_build_primary_response()`, `_derive_analytics_raw()`, `_derive_summary_from_analytics()`, `_derive_trend_from_analytics()` 函式定義
- [x] 4.5 移除 batch pareto (L2024) 中的 `_allow_legacy_fallback()` gate，DuckDB 為唯一路徑
- [x] 4.6 移除 export-cached (L2181) 中的 `_allow_legacy_fallback()` gate，DuckDB 為唯一路徑
- [x] 4.7 刪除 `_allow_legacy_fallback()` 函式定義與 `_REJECT_CACHE_SQL_BATCH_PARETO_FALLBACK_LEGACY_ENABLED` / `_REJECT_CACHE_SQL_EXPORT_FALLBACK_LEGACY_ENABLED` flag 常數
- [x] 4.8 確認 `_build_response_from_spool()` 中的 `_derive_trend_from_analytics()` 呼叫 (L892) 改為由 DuckDB result 提供
- [x] 4.9 更新 `tests/test_reject_dataset_cache.py`：移除 pandas mock，改為驗證 DuckDB path
- [x] 4.10 執行 `pytest tests/test_reject_dataset_cache.py -v` 確認通過

## 5. 驗證與收尾

- [x] 5.1 執行 `pytest tests/ -v` 全域回歸測試
- [x] 5.2 確認四個 service 檔案中不再有 `_derive_` / `_build_primary_response` / `_get_cached_df` 函式定義（grep 驗證）
- [x] 5.3 確認四個 service 檔案中不再有 `redis_df_store.redis_store_df` / `redis_load_df` 大型 DataFrame 呼叫（grep 驗證）
- [x] 5.4 更新 `docs/page_query_architecture_audit_and_ram_phase_plan.md` Phase 5 section：加入實作結果摘要
