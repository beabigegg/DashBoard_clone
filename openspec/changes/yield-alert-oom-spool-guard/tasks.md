## 1. Memory Guard 與 Route 層保護

- [x] 1.1 在 `yield_alert_dataset_cache.py` 新增 import `enforce_dataset_memory_guard`, `maybe_gc_collect` 及環境變數常數（`_VIEW_MAX_INPUT_MB`, `_VIEW_MAX_PROJECTED_RSS_MB`, `_VIEW_WORKING_SET_FACTOR`）
- [x] 1.2 在 `execute_primary_query` 中 `_load_primary_detail_df()` 返回後加入 `enforce_dataset_memory_guard` 呼叫
- [x] 1.3 在 `apply_view` 中取得 `detail_df` 後、計算前加入 `enforce_dataset_memory_guard` 呼叫，末尾加入 `maybe_gc_collect()`
- [x] 1.4 在 `yield_alert_routes.py` 的 `api_yield_alert_query` 和 `api_yield_alert_view` 加入 `except MemoryError` 回傳 503 `SERVICE_UNAVAILABLE`

## 2. Pandas 路徑優化

- [x] 2.1 消除 `_build_heatmap_data` 中 L152/L161 的 `.copy()`，改用 `df.assign(DATE_STR=...)` 或直接 groupby vectorized bucket
- [x] 2.2 優化 `_build_alerts_view`：將 yield_pct / risk_score 等衍生欄位改為 pandas 向量化計算，在 DataFrame 內排序分頁後才轉 dict（僅對當頁 rows 做 iterrows + linkage 匹配）
- [x] 2.3 降低 `_CACHE_MAX_SIZE` 預設值 6 → 3

## 3. Parquet Spool 寫入

- [x] 3.1 在 `yield_alert_dataset_cache.py` 新增 import `store_spooled_df` / `get_spool_file_path`，定義 `_SPOOL_NAMESPACE = "yield_alert_dataset"`
- [x] 3.2 在 `execute_primary_query` 中 `_store_payload` 之後呼叫 `store_spooled_df`（失敗僅 log warning，不阻斷流程）

## 4. DuckDB SQL Runtime

- [x] 4.1 新建 `src/mes_dashboard/services/yield_alert_sql_runtime.py`，建立基礎架構：feature flag（`YIELD_ALERT_SQL_VIEW_ENABLED`）、spool 來源解析、DuckDB connection helper、filter 條件建構
- [x] 4.2 實作 `_build_reason_exclusion_sql`：將 `_load_excluded_reason_tokens` 的排除邏輯轉為 DuckDB SQL 條件（含 reversal 保留邏輯）
- [x] 4.3 實作 summary 聚合 SQL（transaction_qty / scrap_qty / yield_pct）
- [x] 4.4 實作 trend 聚合 SQL（按 granularity 分桶 + groupby）
- [x] 4.5 實作 heatmap 聚合 SQL（station × date 交叉）
- [x] 4.6 實作 station_summary 和 package_summary 聚合 SQL
- [x] 4.7 實作 alerts 聚合 SQL（GROUP BY + HAVING + yield/risk 計算 + ORDER BY + LIMIT/OFFSET 分頁）
- [x] 4.8 實作 filter_options 查詢 SQL（提取 lines/packages/types/functions 唯一值）
- [x] 4.9 組合為 `try_compute_view_from_spool` 入口函數，回傳完整 view result 或 (None, fallback_reason)

## 5. apply_view 整合 DuckDB-first 路徑

- [x] 5.1 在 `apply_view` 函數開頭加入 DuckDB-first 嘗試：呼叫 `try_compute_view_from_spool`，成功則直接回傳
- [x] 5.2 DuckDB 回傳的 alerts 當頁 rows 在 Python 層做 linkage 匹配（複用既有 linkage_exact / linkage_prefix 邏輯）
- [x] 5.3 確認 fallback 路徑（spool miss / DuckDB error / feature flag off）正確進入既有 pandas 邏輯

## 6. 驗證

- [x] 6.1 執行 `pytest tests/ -v -k yield_alert` 確認既有測試通過
- [x] 6.2 手動測試：30 天日期範圍查詢，確認 DuckDB 路徑命中（觀察 log）
- [x] 6.3 手動測試：設定 `YIELD_ALERT_SQL_VIEW_ENABLED=false`，確認 pandas fallback + memory guard 正常運作
- [x] 6.4 比較 DuckDB 與 pandas 路徑對相同查詢的結果一致性
