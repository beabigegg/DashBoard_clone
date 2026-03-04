## Context

`reject-history` 的 two-phase 主查詢 (`POST /api/reject-history/query`) 目前重用 `reject_history/list.sql`。該 SQL 內含 `COUNT(*) OVER()` 與 `OFFSET/FETCH`，原本是為 paginated `/api/reject-history/list` 契約設計。當主查詢走大日期範圍且啟用 batch chunk 時，`reject_dataset_cache` 會透過 offset/limit 迴圈重複執行 list 查詢，導致高成本重算與長尾延遲（已出現 90~150 秒慢查詢）。

同時，`/api/reject-history/list` 仍保留於後端路由與測試中，不能以「直接改 list.sql」方式處理，否則會有分頁契約與 legacy 調用相容風險。

## Goals / Non-Goals

**Goals:**
- 讓 `POST /api/reject-history/query` 改用 primary 專用 SQL，移除對 paginated `list.sql` 的執行耦合。
- 讓 batch chunk 路徑不再以 `offset/limit` 迴圈拉全量，降低 chunk 級重複計算。
- 維持 `/api/reject-history/list` 既有分頁與回應語意不變。
- 維持 `/query`、`/view`、`/export-cached` 既有資料語意與 API 欄位契約不變。

**Non-Goals:**
- 不移除 `/api/reject-history/list` 或其 legacy 路由。
- 不調整業務指標定義（`REJECT_TOTAL_QTY`、`DEFECT_QTY`、policy filter）。
- 不引入新基礎設施（新 DB、新 cache 類型、新第三方依賴）。

## Decisions

### D1: 新增 primary 專用 SQL 模板，不修改 `list.sql` 契約

- Decision: 在 `src/mes_dashboard/sql/reject_history/` 新增主查詢專用 SQL（lot-level、非分頁語意），供 dataset cache 主查詢使用。
- Why: `list.sql` 同時服務 `/list` 與 `/query` 是目前性能與相容性衝突根因。拆分來源可同時滿足性能與相容。
- Alternatives considered:
  - 直接修改 `list.sql`：可改善 `/query` 但高機率破壞 `/list` pagination/total_count 契約。
  - 只調整並行度參數：可緩解但無法消除 SQL 本身重複計算成本。

### D2: `reject_dataset_cache` direct/chunk 路徑統一使用 primary SQL

- Decision: `execute_primary_query()` 的 direct 路徑與 batch chunk 路徑都切到 primary SQL。
- Why: 若僅改 direct 路徑，長範圍查詢（實際主要痛點）仍走舊的 chunk + paginated list 模式，收益有限。
- Alternatives considered:
  - 只改 direct path：大範圍查詢仍受慢查詢影響。
  - 只改 chunk path：短範圍直查仍殘留 list 耦合與語意不一致。

### D3: chunk 執行改為單次查詢，不再依賴 offset/limit 迴圈

- Decision: 每個 chunk 以一次 primary SQL 查詢取得完整 chunk dataset，移除 `offset` 迴圈抓取邏輯。
- Why: 現行做法會在同 chunk 內重跑含排序與 total_count 的查詢多次，放大 DB 成本。
- Alternatives considered:
  - 保留迴圈但調大 page size：只能減少次數，仍有重複計算與語意負擔。

### D4: 將 `/list` 相容性納入硬性回歸防護

- Decision: 保留 `/api/reject-history/list` 路由與 `query_list()` 邏輯不變，並補齊相容性測試。
- Why: 專案仍保留路由、文件與 smoke test 依賴；需要明確防止回歸。
- Alternatives considered:
  - 一併移除 `/list`：牽涉範圍擴大，與本次性能修復目標不一致。

## Risks / Trade-offs

- [Risk] primary SQL 與 list SQL 欄位差異造成後續 pandas 衍生失敗  
  → Mitigation: 明確定義 primary SQL 欄位最小契約，新增單元測試檢查欄位完整性。

- [Risk] chunk 單次查詢結果量過大導致記憶體壓力  
  → Mitigation: 保留既有 batch decomposing、max rows/total rows 與 parquet spill guardrail。

- [Risk] 只優化 `/query` 但未改善其他慢查詢來源  
  → Mitigation: 本次聚焦 reject-history primary path，其他路徑另案處理。

- [Trade-off] 新增一份 SQL 會提高維護成本  
  → Mitigation: 文件化「list for paginated API / primary for dataset cache」分工，避免再度耦合。

## Migration Plan

1. 新增 primary 專用 SQL 並接入 SQL loader。
2. 修改 `reject_dataset_cache` direct 與 chunk 路徑，改用 primary SQL。
3. 保持 `reject_history_service.query_list()` 與 `list.sql` 不變。
4. 補齊測試：
   - `/query` 不再送 `offset/limit` 到 primary SQL 路徑。
   - `/list` 回應 pagination 契約不變。
5. 先在 dev 環境比對慢查詢日誌與前端逾時事件，再推進上線。

Rollback strategy:
- 若新 primary SQL 發生欄位或性能異常，回退 `reject_dataset_cache` 到原 `list.sql` 路徑（保留新 SQL 檔但不啟用）。
- `/list` 路徑因未改動，回退風險低。

## Open Questions

- primary SQL 檔名是否採 `primary.sql` 或 `dataset_primary.sql`（需與現有命名規則一致）？
- 是否需要在 API `meta` 暴露診斷欄位（例如 `primary_sql_source=dedicated`）供線上追蹤？
