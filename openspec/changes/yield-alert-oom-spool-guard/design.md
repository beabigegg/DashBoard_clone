## Context

Yield Alert Center 的 `apply_view`（`yield_alert_dataset_cache.py`）負責從快取載入完整 detail_df 後在記憶體內做 summary / trend / heatmap / station_summary / package_summary / alerts 聚合。30 天 ERP WIP 資料可達數十萬筆，而每次 view 請求會同時產生 5-7 份 DataFrame 副本（`detail_filt` + `tx_df_base` + `scrap_df_base` + `_build_heatmap_data` 的 `.copy()` × 2 + `_build_alerts_view` 的 groupby + 全量 dict list），導致峰值記憶體暴增並 OOM。

專案其他重查詢模組已有完善保護：
- `reject_dataset_cache.py` 使用 `enforce_dataset_memory_guard` + DuckDB SQL runtime（`reject_cache_sql_runtime.py`）
- `trace_routes.py` 使用 RSS guard + async job 路由
- `query_tool_service.py` 使用 `_check_rss_guard`

Yield Alert 僅有 route 層 concurrency rejection，缺乏 service 層保護。

約束條件：
- 不變更 API 回應結構（前端無需修改）
- 不可靜默資料缺失（guard 拒絕時必須明確 503 回應）
- 需可透過 feature flag 關閉 DuckDB 路徑回退 pandas

## Goals / Non-Goals

**Goals:**
- 在 `execute_primary_query` 和 `apply_view` 加入 interactive memory guard 作為安全網
- 將 primary query 結果寫入 parquet spool 磁碟快取
- 建立 `yield_alert_sql_runtime.py`，以 DuckDB 查詢 parquet 完成所有 view 聚合
- `apply_view` 改為 DuckDB-first + pandas fallback 架構
- 優化既有 pandas 路徑（消除 `.copy()`、alerts 向量化分頁）
- 降低 process cache max_size 減少記憶體常駐量

**Non-Goals:**
- 不變更 Oracle primary query SQL
- 不變更前端查詢流程、URL 參數、欄位命名
- 不在此改動中處理其他頁面的 cache 運算
- 不新增或移除 API endpoint

## Decisions

### D1. 複用既有 parquet spool + DuckDB 架構

- **Decision**: 使用 `core/query_spool_store.py` 的 `store_spooled_df` / `get_spool_file_path` 寫入/定位 parquet 檔案，新建 `yield_alert_sql_runtime.py` 做 DuckDB 查詢。
- **Rationale**: reject-history 已驗證此架構可行且穩定，直接複用避免重複建設。
- **Alternatives considered**:
  - Redis-only（現狀）: parquet 編碼 + base64 存入 Redis，載入時仍需完整反序列化到 pandas，無法 out-of-core。
  - pandas 優化 only: 減少 `.copy()` 可降低部分峰值，但無法根本解決大資料量的記憶體問題。

### D2. DuckDB-first + pandas fallback

- **Decision**: `apply_view` 先嘗試 DuckDB SQL 路徑；若 spool 檔案不存在或 DuckDB 不可用，則回退到既有 pandas 路徑（含 memory guard）。
- **Rationale**: 漸進式遷移，確保穩定性。feature flag `YIELD_ALERT_SQL_VIEW_ENABLED` 可隨時關閉。
- **Alternatives considered**:
  - 直接移除 pandas 路徑: 風險過高，無法回退。

### D3. DuckDB SQL 內完成 alerts 排序分頁

- **Decision**: alerts 的 `GROUP BY` + `HAVING` + `ORDER BY` + `LIMIT/OFFSET` 全部在 DuckDB SQL 完成，僅回傳當頁資料。linkage 匹配在 Python 層對當頁 rows 處理。
- **Rationale**: 這是 OOM 的最大貢獻者——原本全量具現化為 Python dict list 後排序再分頁。SQL 內分頁可將記憶體從 O(N) 降到 O(page_size)。
- **Alternatives considered**:
  - pandas 向量化 + iloc 分頁: 仍需載入完整 DataFrame，只是減少 Python dict 數量。

### D4. Interactive memory guard 作為安全網

- **Decision**: 在 pandas fallback 路徑和 primary query 後都加入 `enforce_dataset_memory_guard`，MemoryError 在 route 層轉為 503。
- **Rationale**: DuckDB 路徑失敗時，pandas fallback 仍需保護。guard 提供明確錯誤訊息（非靜默失敗）。
- **Configuration**: `YIELD_ALERT_VIEW_MAX_INPUT_MB=96`, `YIELD_ALERT_VIEW_MAX_PROJECTED_RSS_MB=1100`, `YIELD_ALERT_VIEW_WORKING_SET_FACTOR=2.5`

### D5. 降低 process cache max_size

- **Decision**: `_CACHE_MAX_SIZE` 預設 6 → 3。
- **Rationale**: 6 組完整 DataFrame 在記憶體佔用過高。DuckDB 路徑不需要 process cache（直接讀 parquet），pandas fallback 保留 3 組已足夠。

## Risks / Trade-offs

- **[Risk] DuckDB SQL 語意與 pandas 計算結果微差** → 保留 pandas fallback 路徑做對照；在測試中比較兩路徑輸出一致性。
- **[Risk] parquet spool 磁碟空間** → 複用既有 `QUERY_SPOOL_MAX_BYTES` 上限與自動清理機制。
- **[Risk] DuckDB 依賴引入的記憶體** → DuckDB 本身 memory-mapped 查詢 parquet，RSS 增量遠小於 pandas 全量載入。
- **[Risk] reason exclusion policy 在 SQL 中重建** → 需確保 `_load_excluded_reason_tokens` 的排除邏輯在 SQL 中等價實現。
