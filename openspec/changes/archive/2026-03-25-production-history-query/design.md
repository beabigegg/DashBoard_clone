## Context

MES Dashboard 需要一個獨立的「生產歷程查詢」頁面，以 PJ_TYPE + TrackIn 日期區間為主軸，查詢產品在各站點/機台的生產足跡。版面採上方聚合 Matrix + 下方明細 TABLE，後端採 Oracle 一次查詢 + Parquet spool + DuckDB 衍生視圖的兩層架構。

## Goals / Non-Goals

**Goals:**
- 建立獨立頁面 `/production-history`，支援 PJ_TYPE + 日期區間 + 工單/LOT/Package/BOP/WorkCenter/EQP 組合查詢。
- 上方 Matrix 以 WorkCenter(Group) → Spec → Equipment 三層展開，按月份計數（只顯示有資料的月份）。
- 下方明細 TABLE 25 rows/page，點選 Matrix 節點聯動過濾。
- 全量 CSV 匯出。
- LOT ID 查詢時沿 split chain 追溯 parent LOT。
- 複用現有 Oracle → spool → DuckDB 基礎設施。

**Non-Goals:**
- 不做血緣樹展開（不同於現有 query-tool 的正向/反向追蹤）。
- Phase 1 不含 REJECT / ERP MOVE 良率分析（Phase 2 擴充）。
- 不替換或修改現有 query-tool 頁面。

## Decisions

### 1. 兩層查詢架構 + 分批分段引擎
- **Decision**: 使用 `batch_query_engine` 做時間區間分段查詢。流程：`decompose_by_time_range(start, end, grain_days)` 拆成多個 chunk → `execute_plan(chunks, query_fn)` 逐 chunk 打 Oracle（每 chunk 結果存 Redis，自動 retry transient errors）→ `merge_chunks_to_spool()` 串流合併寫入 Parquet spool → 後續所有操作（Matrix 聚合、篩選、分頁、匯出）走 DuckDB over Parquet。
- **Why**: PJ_TYPE + 180 天可能數萬~數十萬筆，單一 Oracle 查詢風險高（timeout、記憶體）。分段後每 chunk 有記憶體上限（192MB）、row limit 保護，且已完成 chunk 可快取避免重複查詢。複用現有 `batch_query_engine` + `query_spool_store` + `*_sql_runtime` 模式，與 reject/hold/job 等重查詢一致。
- **Alternative**: Oracle 一次查詢不分段；放棄，大區間查詢容易 timeout 且記憶體不可控。

### 2. 主查詢 SQL 設計
- **Decision**: `DW_MES_CONTAINER c JOIN DW_MES_LOTWIPHISTORY h ON c.CONTAINERID = h.CONTAINERID`，所有篩選條件進 WHERE，GROUP BY `CONTAINERNAME, PJ_TYPE, WORKCENTERNAME, SPECNAME, EQUIPMENTID, EQUIPMENTNAME`，取 `MIN(TRACKINTIMESTAMP), MAX(TRACKOUTTIMESTAMP), MIN(TRACKINQTY), MAX(TRACKOUTQTY)`。
- **Why**: 使用者定義的 key = WORKCENTER + SPEC + LOTID + EQUIPMENTID，聚合同一 LOT 在同站同機台的多筆紀錄。
- **Alternative**: 不做 GROUP BY 直接回傳每筆 raw history；放棄，資料量太大且不符使用者期望的聚合粒度。

### 3. LOT ID 查詢的 split chain trace
- **Decision**: 複用現有 `_trace_parents_for_equipment` 邏輯。LOT ID 輸入時，先查 LOTWIPHISTORY，找不到的沿 split chain 追溯 parent，合併結果。PJ_TYPE 查詢不需要 trace（parent/child 同 TYPE 都會出現）。
- **Why**: `-01C` 等拆批 LOT 只有後段紀錄，需往上找 parent 才有前段歷程。

### 4. 版面：上方 Matrix + 下方 TABLE
- **Decision**: 上方為 HierarchyTable 風格的聚合 Matrix（WorkCenter Group → Spec → Equipment，動態月份欄位計數），下方為分頁明細表。點選 Matrix 任一層級節點，後端以 DuckDB 查詢對應的明細分頁。
- **Why**: 符合使用者提供的 mockup，且與現有 hold-overview 的 Matrix + Detail 模式一致。
- **Alternative**: 左右分割版面；放棄，依使用者要求改為上下。

### 5. 篩選器互動模式
- **Decision**: 方案 B — 全部條件一次送後端。使用者填好所有篩選條件 → 點「查詢」→ Oracle 查詢 → 建立 spool → 回傳首頁結果 + Matrix 摘要。後續 Matrix 聯動、分頁走 DuckDB。換主條件需重新查詢。
- **Why**: PJ_TYPE + 30 天可能數萬筆，前端即時過濾撐不住。

### 6. 獨立頁面路由
- **Decision**: 新增路由 `/production-history`，在 `nativeModuleRegistry.js` + `routeContracts.js` 註冊，獨立於 query-tool。
- **Why**: 使用者要求獨立頁面，非 query-tool 的 tab。

### 7. 後端端點設計
- **Decision**: 新增 Blueprint `production_history_bp`，prefix `/api/production-history`。
  - `POST /query` — 主查詢（Oracle → spool → 回傳首頁 + Matrix 摘要）
  - `POST /page` — 明細分頁（DuckDB over spool）
  - `POST /matrix` — Matrix 聚合（DuckDB over spool，按月份 GROUP BY）
  - `GET /export` — 全量 CSV 串流匯出（DuckDB over spool）
- **Why**: 與現有 yield-alert / reject-history 的 spool + view 端點模式一致。

### 8. DuckDB sql_runtime 模組
- **Decision**: 新增 `production_history_sql_runtime.py`，提供 `compute_matrix_view` 和 `compute_detail_page` 函式，參考 `yield_alert_sql_runtime.py` 結構。
- **Why**: 統一 DuckDB over Parquet 的查詢模式，便於維護和 feature flag 控制。

### 9. 慢查詢通道 + 全域並行控制
- **Decision**: chunk query function 使用 `read_sql_df_slow`（獨立連線池 + 信號量 + 300 秒 timeout）。主查詢入口使用 `acquire_heavy_query_slot(owner_id)` 取得全域重查詢 slot（最多 3 個同時執行），查詢完畢或異常時 `release_heavy_query_slot`。
- **Why**: 與所有現有重查詢一致（reject/hold/yield-alert/resource），防止拖垮正常 API 服務。
- **Alternative**: 走 `read_sql_df` 正常通道；放棄，會佔用正常請求的連線池。

### 10. Feature Flags
- **Decision**: 新增三個環境變數：
  - `PROD_HISTORY_SQL_VIEW_ENABLED` (default `true`) — DuckDB runtime 開關，`false` 時降級回 pandas
  - `PROD_HISTORY_ASYNC_ENABLED` (default `false`) — Phase 2 預留 RQ async 開關
  - `PROD_HISTORY_ENGINE_GRAIN_DAYS` (default `31`) — 分段天數
- **Why**: 與現有 `YIELD_ALERT_SQL_VIEW_ENABLED` / `HOLD_HISTORY_SQL_VIEW_ENABLED` 模式一致，可逐步啟用/停用。

### 11. Heavy Query Telemetry
- **Decision**: 在 `heavy_query_telemetry.py` 記錄 production-history 路由的 guard_reject / memory_error 計數。新端點的 query latency 記錄到 `record_query_latency()`。
- **Why**: Admin Dashboard Performance Tab 和 Worker Tab 需要可見性。

### 12. RQ Async (Phase 2 預留)
- **Decision**: Phase 1 走同步 + 分批（與 hold/yield-alert 一致）。預留 `PROD_HISTORY_ASYNC_ENABLED` flag，Phase 2 視實測需求決定是否引入 async worker。
- **Why**: 同步分批已有 chunk 級快取 + 記憶體保護 + timeout 控制，足以應對 180 天區間。async 增加複雜度（需 worker 進程、job 狀態輪詢 UI），不急。

### 13. Admin Dashboard 同步
- **Decision**: 無需額外修改。Heavy query slots gauge 已是全域的，自動涵蓋新查詢。Performance Tab 的 query latency 會自動記錄新端點（透過 `record_query_latency`）。Phase 2 若加 RQ async，再更新 WorkerTab 的 queue 表。
- **Why**: 現有 admin 監控基礎設施已足夠觀測新功能的健康狀態。

## Risks / Trade-offs

- [Risk] PJ_TYPE + 長日期區間（如 6 個月）可能產生數十萬筆 Oracle 結果 → Mitigation: 限制日期區間上限（MAX_DATE_RANGE_DAYS = 180）+ 分批引擎 + 每 chunk 記憶體上限 192MB + row limit。
- [Risk] 多個使用者同時查詢拖垮系統 → Mitigation: `acquire_heavy_query_slot` 限制全域最多 3 個重查詢 + `read_sql_df_slow` 信號量限制 2 個同時 DB 查詢。
- [Risk] Spool 檔案過大佔用磁碟 → Mitigation: 複用現有 spool capacity 管理（2GB 上限、5 分鐘清理、6 小時 TTL）。
- [Risk] Matrix 月份欄位過多（跨年查詢） → Mitigation: 前端動態生成欄位，只顯示有資料的月份；最多 7 個月（配合 180 天上限）。
- [Trade-off] 全部條件送後端意味著換任一篩選都要重打 Oracle → Acceptable: 分批引擎有 chunk 級快取，相似查詢可復用已快取的 chunk。
