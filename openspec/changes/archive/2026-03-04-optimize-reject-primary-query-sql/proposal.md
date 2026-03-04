## Why

目前 reject-history 的 `POST /api/reject-history/query` 主查詢路徑重用 `list.sql`（含 `COUNT(*) OVER()` 與 `OFFSET/FETCH` 分頁語意），在大日期範圍與 batch chunk 場景下會產生高成本重算，已出現多次 90~150 秒慢查詢與前端逾時。`list.sql` 同時服務 legacy `/api/reject-history/list`，直接改動容易破壞既有分頁契約，因此需要將 primary 查詢來源與 list 查詢解耦。

## What Changes

- 新增 reject-history primary 專用 SQL（lot-level、非分頁語意），供 dataset cache 主查詢使用。
- 調整 `reject_dataset_cache.execute_primary_query()`（direct 與 engine chunk 路徑）改用 primary 專用 SQL，不再依賴 `list.sql` 的 `offset/limit` 分頁迴圈。
- 保留 `list.sql` 與 `GET /api/reject-history/list` 現有行為與回應契約（排序、分頁、`TOTAL_COUNT`）不變。
- 補齊回歸防護：新增/調整測試以驗證 `/list` 契約未變，且 `/query` 查詢來源已切換到 primary 專用 SQL。
- 保持 `/query`、`/view`、`/export-cached` 的資料語意與欄位契約不變（非 breaking）。

## Capabilities

### New Capabilities
- `reject-history-primary-query-source-isolation`: 為 primary query 建立獨立資料來源，避免與 paginated list SQL 耦合，降低大範圍查詢延遲與逾時風險。

### Modified Capabilities
- `reject-history-api`: 調整 primary query 的實作要求，明確規範 `/query` 與 `/list` 查詢路徑解耦，且 `/list` 契約必須維持相容。
- `batch-query-resilience`: 調整 reject-history chunk 執行要求，移除以 paginated list SQL 疊代抓全量的依賴，降低 chunk 級重複計算成本。

## Impact

- Affected backend code:
  - `src/mes_dashboard/services/reject_dataset_cache.py`
  - `src/mes_dashboard/services/reject_history_service.py`（若需擴充 SQL template slot）
  - `src/mes_dashboard/sql/reject_history/`（新增 primary 專用 SQL）
  - `src/mes_dashboard/routes/reject_history_routes.py`（僅在需要補充 meta/診斷資訊時）
- Affected tests:
  - `tests/test_reject_dataset_cache.py`
  - `tests/test_reject_history_service.py`
  - `tests/test_reject_history_routes.py`
- API surface:
  - 無新增或移除 endpoint
  - 無既有參數/回應破壞性變更
- Dependencies/infra:
  - 無新增外部依賴
  - 可沿用既有 slow-query engine、batch engine、cache/spool 機制
