## Why

批次追蹤工具 (`/query-tool`) 與中段製程不良追溯分析 (`/mid-section-defect`) 是本專案中查詢複雜度最高的兩個頁面。兩者都需要解析 LOT 血緣關係（拆批 split + 併批 merge），但各自實作了獨立的追溯邏輯，導致：

1. **效能瓶頸**：mid-section-defect 使用 Python 多輪 BFS 追溯 split chain（`_bfs_split_chain()`，每次 3-16 次 DB round-trip），加上 `genealogy_records.sql` 對 48M 行的 `HM_LOTMOVEOUT` 全表掃描（30-120 秒）。
2. **安全風險**：query-tool 的 `_build_in_filter()` 使用字串拼接建構 IN 子句（`query_tool_service.py:156-174`），`_resolve_by_lot_id()` / `_resolve_by_serial_number()` / `_resolve_by_work_order()` 系列函數傳入空 params `read_sql_df(sql, {})`——值直接嵌入 SQL 字串中，存在 SQL 注入風險。
3. **缺乏防護**：query-tool 無 rate limit、無 cache，高併發時可打爆 DB connection pool（Production pool_size=10, max_overflow=20）。
4. **重複程式碼**：兩個 service 各自維護 split chain 追溯、merge lookup、batch IN 分段等相同邏輯。

Oracle 19c 的 `CONNECT BY NOCYCLE` 可以用一條 SQL 取代整套 Python BFS，將 3-16 次 DB round-trip 縮減為 1 次。備選方案為 Oracle 19c 支援的 recursive `WITH` (recursive subquery factoring)，功能等價但可讀性更好。split/merge 的資料來源 (`DW_MES_CONTAINER.SPLITFROMID` + `DW_MES_PJ_COMBINEDASSYLOTS`) 完全不需碰 `HM_LOTMOVEOUT`，可消除 48M 行全表掃描。

**邊界聲明**：本變更為純後端內部重構，不新增任何 API endpoint，不改動前端。既有 API contract 向下相容（URL、request/response 格式不變），僅新增可選的 `full_history` query param 作為向下相容擴展。後續的前端分段載入和新增 API endpoints 列入獨立的 `trace-progressive-ui` 變更。

## What Changes

- 建立統一的 `LineageEngine` 模組（`src/mes_dashboard/services/lineage_engine.py`），提供 LOT 血緣解析共用核心：
  - `resolve_split_ancestors()` — 使用 `CONNECT BY NOCYCLE` 單次 SQL 查詢取代 Python BFS（備選: recursive `WITH`，於 SQL 檔案中以註解標註替代寫法）
  - `resolve_merge_sources()` — 從 `DW_MES_PJ_COMBINEDASSYLOTS` 查詢併批來源
  - `resolve_full_genealogy()` — 組合 split + merge 為完整血緣圖
  - 設計為 profile-agnostic 的公用函數，未來其他頁面（wip-detail、lot-detail）可直接呼叫，但本變更僅接入 mid-section-defect 和 query-tool
- 建立統一的 `EventFetcher` 模組，提供帶 cache + rate limit 的批次事件查詢，封裝既有的 domain 查詢（history、materials、rejects、holds、jobs、upstream_history）。
- 重構 `mid_section_defect_service.py`：以 `LineageEngine` 取代 `_bfs_split_chain()` + `_fetch_merge_sources()` + `_resolve_full_genealogy()`；以 `EventFetcher` 取代 `_fetch_upstream_history()`。
- 重構 `query_tool_service.py`：以 `QueryBuilder` bind params 全面取代 `_build_in_filter()` 字串拼接；加入 route-level rate limit 和 cache 對齊 mid-section-defect 既有模式。
- 新增 SQL 檔案：
  - `sql/lineage/split_ancestors.sql`（CONNECT BY NOCYCLE 實作，檔案內包含 recursive WITH 替代寫法作為 Oracle 版本兼容備註）
  - `sql/lineage/merge_sources.sql`（從 `sql/mid_section_defect/merge_lookup.sql` 遷移）
- 廢棄 SQL 檔案（標記 deprecated，保留一個版本後刪除）：
  - `sql/mid_section_defect/genealogy_records.sql`（48M row HM_LOTMOVEOUT 全掃描不再需要）
  - `sql/mid_section_defect/split_chain.sql`（由 lineage CONNECT BY 取代）
- 為 query-tool 的 `lot_split_merge_history.sql` 加入雙模式查詢：
  - **fast mode**（預設）：`TXNDATE >= ADD_MONTHS(SYSDATE, -6)` + `FETCH FIRST 500 ROWS ONLY`——涵蓋近半年追溯，回應 <5s
  - **full mode**：前端傳入 `full_history=true` 時不加時間窗，保留完整歷史追溯能力，走 `read_sql_df_slow` (120s timeout)
  - query-tool route 新增 `full_history` boolean query param，service 依此選擇 SQL variant

## Capabilities

### New Capabilities

- `lineage-engine-core`: 統一 LOT 血緣解析引擎。提供 `resolve_split_ancestors()`（CONNECT BY NOCYCLE，`LEVEL <= 20` 上限）、`resolve_merge_sources()`、`resolve_full_genealogy()` 三個公用函數。全部使用 `QueryBuilder` bind params，支援批次 IN 分段（`ORACLE_IN_BATCH_SIZE=1000`）。函數簽名設計為 profile-agnostic，接受 `container_ids: List[str]` 並回傳字典結構，不綁定特定頁面邏輯。
- `event-fetcher-unified`: 統一事件查詢層，封裝 cache key 生成（格式: `evt:{domain}:{sorted_cids_hash}`）、L1/L2 layered cache（對齊 `core/cache.py` LayeredCache 模式）、rate limit bucket 配置（對齊 `configured_rate_limit()` 模式）。domain 包含 `history`、`materials`、`rejects`、`holds`、`jobs`、`upstream_history`。
- `query-tool-safety-hardening`: 修復 query-tool SQL 注入風險——`_build_in_filter()` 和 `_build_in_clause()` 全面改用 `QueryBuilder.add_in_condition()`，消除 `read_sql_df(sql, {})` 空 params 模式；加入 route-level rate limit（對齊 `configured_rate_limit()` 模式：resolve 10/min, history 20/min, association 20/min）和 response cache（L2 Redis, 60s TTL）。

### Modified Capabilities

- `cache-indexed-query-acceleration`: mid-section-defect 的 genealogy 查詢從 Python BFS 多輪 + HM_LOTMOVEOUT 全掃描改為 CONNECT BY 單輪 + 索引查詢。
- `oracle-query-fragment-governance`: `_build_in_filter()` / `_build_in_clause()` 廢棄，統一收斂到 `QueryBuilder.add_in_condition()`。新增 `sql/lineage/` 目錄遵循既有 SQLLoader 慣例。

## Impact

- **Affected code**:
  - 新建: `src/mes_dashboard/services/lineage_engine.py`, `src/mes_dashboard/sql/lineage/split_ancestors.sql`, `src/mes_dashboard/sql/lineage/merge_sources.sql`
  - 重構: `src/mes_dashboard/services/mid_section_defect_service.py` (1194L), `src/mes_dashboard/services/query_tool_service.py` (1329L), `src/mes_dashboard/routes/query_tool_routes.py`
  - 廢棄: `src/mes_dashboard/sql/mid_section_defect/genealogy_records.sql`, `src/mes_dashboard/sql/mid_section_defect/split_chain.sql` (由 lineage 模組取代，標記 deprecated 保留一版)
  - 修改: `src/mes_dashboard/sql/query_tool/lot_split_merge_history.sql` (加時間窗 + row limit)
- **Runtime/deploy**: 無新依賴，仍為 Flask/Gunicorn + Oracle + Redis。DB query pattern 改變但 connection pool 設定不變。
- **APIs/pages**: `/query-tool` 和 `/mid-section-defect` 既有 API contract 向下相容——URL、輸入輸出格式、HTTP status code 均不變，純內部實作替換。向下相容的擴展：query-tool API 新增 rate limit header（`Retry-After`，對齊 `rate_limit.py` 既有實作）；query-tool split-merge history 新增可選 `full_history` query param（預設 false = fast mode，不傳時行為與舊版等價）。
- **Performance**: 見下方 Verification 章節的量化驗收基準。
- **Security**: query-tool IN clause SQL injection 風險消除。所有 `_build_in_filter()` / `_build_in_clause()` 呼叫點改為 `QueryBuilder.add_in_condition()`。
- **Testing**: 需新增 LineageEngine 單元測試，並建立 golden test 比對 BFS vs CONNECT BY 結果一致性。既有 mid-section-defect 和 query-tool 測試需更新 mock 路徑。

## Verification

效能驗收基準——所有指標須在以下條件下量測：

**測試資料規模**:
- LOT 血緣樹: 目標 seed lot 具備 ≥3 層 split depth、≥50 ancestor nodes、至少 1 條 merge path
- mid-section-defect: 使用 TMTT detection 產出 ≥10 seed lots 的日期範圍查詢
- query-tool: resolve 結果 ≥20 lots 的 work order 查詢

**驗收指標**（冷查詢 = cache miss，熱查詢 = L2 Redis hit）:

| 指標 | 現況 (P95) | 目標 (P95) | 條件 |
|------|-----------|-----------|------|
| mid-section-defect genealogy（冷） | 30-120s | ≤8s | CONNECT BY 單輪，≥50 ancestor nodes |
| mid-section-defect genealogy（熱） | 3-5s (L2 hit) | ≤1s | Redis cache hit |
| query-tool lot_split_merge_history fast mode（冷） | 無上限（可 >120s timeout） | ≤5s | 時間窗 6 個月 + FETCH FIRST 500 ROWS |
| query-tool lot_split_merge_history full mode（冷） | 同上 | ≤60s | 無時間窗，走 `read_sql_df_slow` 120s timeout |
| LineageEngine.resolve_split_ancestors（冷） | N/A (新模組) | ≤3s | ≥50 ancestor nodes, CONNECT BY |
| DB connection 佔用時間 | 3-16 round-trips × 0.5-2s each | 單次 ≤3s | 單一 CONNECT BY 查詢 |

**安全驗收**:
- `_build_in_filter()` 和 `_build_in_clause()` 零引用（grep 確認）
- 所有含使用者輸入的查詢（resolve_by_lot_id, resolve_by_serial_number, resolve_by_work_order 等）必須使用 `QueryBuilder` bind params，不可字串拼接。純靜態 SQL（無使用者輸入）允許空 params

**結果一致性驗收**:
- Golden test: 選取 ≥5 個已知血緣結構的 LOT，比對 BFS vs CONNECT BY 輸出的 `child_to_parent` 和 `cid_to_name` 結果集合完全一致

## Non-Goals

- 前端 UI 改動不在此變更範圍內（前端分段載入和漸進式 UX 列入後續 `trace-progressive-ui` 變更）。
- 不新增任何 API endpoint——既有 API contract 向下相容（僅新增可選 query param `full_history` 作為擴展）。新增 endpoint 由後續 `trace-progressive-ui` 負責。
- 不改動 DB schema、不建立 materialized view、不使用 PARALLEL hints——所有最佳化在應用層（SQL 改寫 + Python 重構 + Redis cache）完成。
- 不改動其他頁面（wip-detail、lot-detail 等）的查詢邏輯——`LineageEngine` 設計為可擴展，但本變更僅接入兩個目標頁面。
- 不使用 Oracle PARALLEL hints（在 connection pool 環境下行為不可預測，不做為最佳化手段）。

## Dependencies

- 無前置依賴。本變更可獨立實施。
- 後續 `trace-progressive-ui` 依賴本變更完成後的 `LineageEngine` 和 `EventFetcher` 模組。

## Risks

| 風險 | 緩解 |
|------|------|
| CONNECT BY 遇超大血緣樹（>10000 ancestors）效能退化 | `LEVEL <= 20` 上限 + `NOCYCLE` 防循環；與目前 BFS `bfs_round > 20` 等效。若 Oracle 19c 執行計劃不佳，SQL 檔案內含 recursive `WITH` 替代寫法可快速切換 |
| 血緣結果與 BFS 版本不一致（regression） | 建立 golden test：用 ≥5 個已知 LOT 比對 BFS vs CONNECT BY 輸出，CI gate 確保結果集合完全一致 |
| 重構範圍橫跨兩個大 service（2500+ 行） | 分階段：先重構 mid-section-defect（有 cache+lock 保護，regression 風險較低），再做 query-tool |
| `genealogy_records.sql` 廢棄後遺漏引用 | grep 全域搜索確認無其他引用點；SQL file 標記 deprecated 保留一個版本後刪除 |
| query-tool 新增 rate limit 影響使用者體驗 | 預設值寬鬆（resolve 10/min, history 20/min），與 mid-section-defect 既有 rate limit 對齊，回應包含 `Retry-After` header |
| `QueryBuilder` 取代 `_build_in_filter()` 時漏改呼叫點 | grep 搜索 `_build_in_filter` 和 `_build_in_clause` 所有引用，逐一替換並確認 0 殘留引用 |
