## Why

目前 reject-history 在快取後的互動查詢仍以 pandas 在 worker 記憶體中做全表 filter/groupby/copy，導致大範圍查詢時 RSS 長時間居高不下，觸發 memory guard、batch-pareto 被拒與 worker restart。既有 parquet spool 已存在，應改為「快取後 SQL 化」以降低峰值記憶體並保留既有 API 契約。

## What Changes

- 新增 reject-history 的 cache-SQL 執行層（DuckDB），優先對 parquet spool / cache 資料做 SQL 查詢與聚合，避免回載整包 pandas DataFrame 再運算。
- 第一階段：`/api/reject-history/batch-pareto` 先改為 DuckDB 路徑（高收益、低風險），維持既有 cross-filter、top80、top20 與回應 schema。
- 第二階段：`/api/reject-history/view` 改為 SQL 化（summary/trend 聚合與明細分頁皆走 SQL），減少 in-memory 中間資料。
- 第三階段：`/api/reject-history/export-cached` 改為串流匯出，避免先 `to_dict` 全量載入記憶體。
- 保留現有 worker / interactive memory guard 作為最後保護；待 SQL 化穩定後再依監控數據調整 guard 門檻。
- 補齊可觀測性與回歸測試，確保前端提示、明細資料語意與匯出完整性維持相容（非 breaking）。

## Capabilities

### New Capabilities
- `reject-history-cache-sql-runtime`: 在 reject-history cache/spool 資料上提供 SQL 執行能力（DuckDB）與查詢路由，將互動查詢從 pandas 全表運算轉為 SQL pushdown / 聚合。

### Modified Capabilities
- `reject-history-api`: 調整 `/batch-pareto`、`/view`、`/export-cached` 的後端計算路徑要求，明確規範以 cache-SQL 為主、回應契約保持不變。
- `reject-history-pareto-materialized-aggregate`: 調整 materialized miss/fallback 行為，要求優先落到 cache-SQL 計算路徑，而非 DataFrame 全表 regroup。
- `reject-history-detail-export-parity`: 擴充匯出要求為串流輸出，同時維持與目前篩選條件一致的資料範圍與欄位語意。

## Impact

- Affected backend code:
  - `src/mes_dashboard/services/reject_dataset_cache.py`
  - `src/mes_dashboard/services/reject_pareto_materialized.py`
  - `src/mes_dashboard/core/query_spool_store.py`（讀取介面/metadata 支援 SQL runtime）
  - `src/mes_dashboard/routes/reject_history_routes.py`
  - `src/mes_dashboard/sql/reject_history/`（新增/調整 SQL 片段）
- Affected tests:
  - `tests/test_reject_dataset_cache.py`
  - `tests/test_reject_history_routes.py`
  - `tests/test_reject_pareto_materialized.py`
  - 新增 cache-SQL runtime 與串流匯出測試
- API surface:
  - 不新增 endpoint
  - 不變更既有參數與回應 schema（非 breaking）
- Dependencies/infra:
  - 新增 DuckDB Python 依賴
  - 可能新增少量 SQL runtime 相關 env 開關（啟用、fallback、併發/記憶體上限）
