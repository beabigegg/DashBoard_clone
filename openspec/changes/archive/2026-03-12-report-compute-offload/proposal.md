## Why

報表系統的 view 階段存在兩個問題：(1) resource-history 和 hold-history 每次 /view 請求都從 Redis 反序列化完整 DataFrame 再跑 Pandas groupby，無記憶體保護且浪費 primary query 已有的分段處理優勢；(2) 所有歷史報表的 view 計算（篩選/排序/分頁/聚合）完全在 server 端執行，使用者每次操作 filter 或翻頁都觸發 5-16 條 DuckDB/Pandas SQL，一次分析 session 產生 50-150 條 server-side query。透過將 view 計算從 server Pandas 遷移到 server DuckDB（out-of-core），再進一步卸載到前端 DuckDB-WASM，可消除 view 階段的記憶體風險並減少 80-90% 的 server view 請求。

## What Changes

### Phase 0：resource-history / hold-history 引入 Parquet Spool
- resource-history 和 hold-history 的 primary query 已使用 `batch_query_engine` 分段查詢，但合併結果仍存入 Redis 全量 DataFrame。改為使用 `merge_chunks_to_spool()` 流式寫入 Parquet spool，與 yield-alert / reject-history 對齊
- 查詢記憶體保護 (`enforce_dataset_memory_guard`) 在分段處理 + DuckDB out-of-core 架構下不再需要於查詢層級拒絕請求，改由分段處理本身提供保護

### Track A：resource-history / hold-history 引入 DuckDB View
- 新增 `resource_history_sql_runtime.py` 和 `hold_history_sql_runtime.py`，將現有 Pandas view 邏輯翻譯為 DuckDB SQL（模式同 `yield_alert_sql_runtime.py`）
- View 階段從 Redis → Pandas 改為 Parquet Spool → DuckDB `read_parquet()` out-of-core 查詢
- 加入 feature flag (`RESOURCE_HISTORY_SQL_VIEW_ENABLED`, `HOLD_HISTORY_SQL_VIEW_ENABLED`) 允許漸進切換

### Track B：前端 DuckDB-WASM 計算卸載
- 新增後端 Parquet spool 下載 API endpoint，讓前端可直接取得查詢結果的 Parquet 檔案
- 前端引入 `@duckdb/duckdb-wasm`，在 Web Worker 中載入 Parquet 並執行本地 SQL 查詢
- yield-alert-center 和 reject-history 的 view 操作（篩選/排序/分頁/聚合子視圖）遷移到前端 DuckDB-WASM 執行
- Risk score / risk level 計算遷移到前端（純算術公式）
- 設定資料量閾值：小型查詢 (<5,000 筆) 走全量 JSON + JS Array，大型查詢走 Parquet + DuckDB-WASM

## Capabilities

### New Capabilities
- `parquet-spool-view-engine`: 通用的 Parquet Spool → DuckDB out-of-core view 計算引擎模式，涵蓋 spool 寫入、DuckDB SQL runtime、feature flag 切換
- `frontend-duckdb-wasm`: 前端 DuckDB-WASM 整合，包含 parquet 下載 API、Web Worker 架構、client-side SQL 查詢、資料量閾值切換策略

### Modified Capabilities
- `resource-dataset-cache`: View 階段從 Redis → Pandas 改為 Parquet Spool → DuckDB out-of-core；primary query 使用 `merge_chunks_to_spool()` 流式輸出
- `hold-dataset-cache`: 同 resource-dataset-cache 的改造
- `frontend-compute-shift`: 擴充為包含 DuckDB-WASM 路徑，新增 Parquet 傳輸和 Web Worker 計算模式

## Impact

- **後端 services**：新增 2 個 sql_runtime 模組；修改 2 個 dataset_cache 模組加入 spool 輸出；新增 1 個 parquet 下載 route
- **前端 dependencies**：新增 `@duckdb/duckdb-wasm` (~4MB gzip)；新增 Web Worker 檔案
- **前端 components**：修改 yield-alert-center/App.vue 和 reject-history/App.vue 的 view 資料流
- **API 契約**：新增 `GET /api/spool/{namespace}/{query_id}.parquet` endpoint；現有 /view API 不變（server fallback 保留）
- **配置**：新增 feature flags（`*_SQL_VIEW_ENABLED`）；Vite 需配置 COOP/COEP headers（DuckDB-WASM SharedArrayBuffer 需要）
- **瀏覽器相容性**：DuckDB-WASM 需 Chrome 92+ / Firefox 79+；不支援時 fallback 到 server-side view
