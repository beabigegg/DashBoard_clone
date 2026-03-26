## Context

報表系統採用兩階段查詢架構：primary query (Oracle → cache) 和 view query (cache → 衍生計算 → JSON)。yield-alert 和 reject-history 已完成 Parquet Spool + DuckDB out-of-core view 遷移，但 resource-history 和 hold-history 的 view 階段仍從 Redis 反序列化全量 DataFrame 跑 Pandas groupby，無記憶體保護。此外，所有報表的 view 計算完全在 server 端執行，使用者每次操作都打 server。

關鍵發現：resource-history 和 hold-history 的 primary query 已使用 `batch_query_engine` 的 `decompose_by_time_range` + `execute_plan` 做分段查詢，但合併時仍走全量 DataFrame → Redis 路徑，分段處理的記憶體優勢在 view 階段被浪費。

## Goals / Non-Goals

**Goals:**
- resource-history / hold-history view 階段消除 Pandas，改用 DuckDB out-of-core
- primary query 使用 `merge_chunks_to_spool()` 流式寫 Parquet，消除全量 DataFrame 需求
- 查詢層級記憶體保護 (`enforce_dataset_memory_guard`) 由分段處理機制取代，不再拒絕查詢
- 前端引入 DuckDB-WASM，yield-alert / reject-history 的 view 操作可在瀏覽器端執行
- 設計可漸進切換的 feature flag 機制

**Non-Goals:**
- 不改變 primary query 的 Oracle 查詢邏輯
- 不遷移 material-trace、mid-section-defect 等追溯類模組（BFS 模式不同）
- 不遷移 job-query、excel-query（優先級低）
- 不改變現有 /view API 的 response 格式（保持向下相容）
- 不實作 IndexedDB 前端快取（Phase 3，本次不含）

## Decisions

### D1：resource-history / hold-history 的 spool 輸出使用 `merge_chunks_to_spool()`

**選擇**：複用現有 `batch_query_engine.merge_chunks_to_spool()`，而非引入新的序列化路徑。

**理由**：
- `merge_chunks_to_spool()` 已被 reject-history 驗證，支援流式寫入（峰值記憶體 = 1 chunk）
- 支援 `max_total_rows` 和 `overflow_mode`，提供行數上限保護
- 替代方案（全量 DataFrame → `to_parquet()`）需要完整 DataFrame 在記憶體中，違背分段處理初衷

### D2：DuckDB SQL runtime 每模組獨立一個檔案

**選擇**：新增 `resource_history_sql_runtime.py` 和 `hold_history_sql_runtime.py`，每模組獨立。

**理由**：
- 與 `yield_alert_sql_runtime.py`、`reject_cache_sql_runtime.py` 模式一致
- 每模組的 sub-view SQL 邏輯差異大（resource 有 workcenter × date 矩陣，hold 有 duration bucket），不適合通用化
- 替代方案（通用 SQL runtime）會導致過度抽象，增加維護成本

### D3：前端使用 DuckDB-WASM + Web Worker 而非純 JS Array

**選擇**：引入 `@duckdb/duckdb-wasm` 在 Web Worker 中執行 SQL。

**理由**：
- 資料量可達 >10,000 筆，純 JS Array 在 10 欄 GROUP BY 去重時效能不足
- 前後端 DuckDB SQL 語法完全相容，可直接移植後端 SQL
- Parquet 格式比 JSON 壓縮比高 3-7x，節省傳輸頻寬
- Web Worker 避免阻塞 UI 線程
- 替代方案（sql.js / AlaSQL）：SQL 方言不同，無法直接復用後端 SQL

### D4：Parquet 下載通過專用 API endpoint 而非直接暴露 spool 目錄

**選擇**：新增 `GET /api/spool/{namespace}/{query_id}.parquet` endpoint。

**理由**：
- spool 目錄是內部實作細節，不應直接暴露
- endpoint 可驗證 query_id 合法性 + 檢查 TTL 過期
- 已有 `query_spool_store.get_spool_file_path()` 提供 path traversal 防護
- 可加入 Content-Length header 讓前端預判檔案大小

### D5：資料量閾值策略 — 小查詢走 JSON、大查詢走 Parquet

**選擇**：以 alert/detail 總筆數 5,000 為閾值，小查詢直接回傳全量 JSON（前端 JS Array 操作），大查詢回傳 parquet 下載 URL（前端 DuckDB-WASM）。

**理由**：
- <5,000 筆的 JSON (~1-2MB) 對大多數瀏覽器輕鬆處理
- 避免小查詢也載入 4MB WASM 的開銷
- 後端 /view response 增加 `spool_download_url` 欄位，前端根據筆數自動決定策略
- 閾值可透過 config 調整

### D6：查詢記憶體保護由分段處理取代，不再拒絕查詢

**選擇**：移除 view 階段的 `enforce_dataset_memory_guard`，保留 `max_total_rows` 和 worker-level guard。

**理由**：
- 分段查詢 (50K/chunk) + 流式合併 + DuckDB out-of-core = 任何階段都不會有全量 DataFrame 在記憶體
- `enforce_dataset_memory_guard` 的「拒絕查詢」行為不友好，分段處理本身就是更好的保護
- 保留 `_REJECT_ENGINE_MAX_TOTAL_ROWS` (200,000) 防止 spool 無限膨脹
- 保留 `worker_memory_guard.py` 的 worker 進程級保護（非查詢級）

## Risks / Trade-offs

- **[DuckDB-WASM 瀏覽器相容性]** → SharedArrayBuffer 需 COOP/COEP headers (Chrome 92+, Firefox 79+)；不支援時 fallback 到 server-side /view API（現有路徑不刪除）
- **[WASM 初始載入延遲]** → DuckDB-WASM ~4MB gzip 一次性載入；可用 Service Worker 快取緩解
- **[行動裝置記憶體]** → Parquet >50MB 可能 OOM；設定前端閾值，超過走 server fallback
- **[前後端計算結果一致性]** → 同 DuckDB SQL dialect + banker's rounding (已有 `compute.js` 先例)；需建立 parity 測試
- **[Parquet endpoint 安全性]** → 已有 `query_spool_store` 的 path traversal 防護 + query_id 校驗；加入 CSRF token 驗證
- **[Feature flag 切換期間]** → 新舊路徑並存，需確保 response 格式一致；用 flag 控制漸進切換

## Migration Plan

1. **Phase 0**：resource-history / hold-history dataset_cache 加入 `merge_chunks_to_spool()` 輸出（與現有 Redis 路徑並存）
2. **Track A**：新增 DuckDB sql_runtime，feature flag 預設 disabled → 灰度測試 → 預設 enabled → 移除 Pandas view fallback
3. **Track B**：新增 parquet 下載 API → 前端引入 DuckDB-WASM → yield-alert / reject-history view 遷移 → 灰度測試
4. **Rollback**：所有 feature flag 設為 disabled 即回到原始 Pandas/server-side 路徑

## Open Questions

- COOP/COEP headers 是否會影響現有 portal-shell 的跨源嵌入？需測試
- DuckDB-WASM 的 `read_parquet()` 在 Web Worker 中是否支援 HTTP Range Request (partial download)？可進一步優化大檔案載入
