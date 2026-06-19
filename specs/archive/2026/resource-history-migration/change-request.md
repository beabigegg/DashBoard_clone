# Change Request

## Original Request

[P2] Resource History 遷移至 `BaseChunkedDuckDBJob`，修復 `export_csv` 全量查詢 OOM 風險，`iterrows` 改 DuckDB SQL。

**實作前必須完整閱讀 `docs/architecture/query-dataflow-unification.md`，尤其是 §3 遷移計畫 P2 行（resource_history_service.py + resource_dataset_cache.py）、§1.4 OOM 風險點第 4 名。本提案依賴 `eap-alarm-unified-job-poc` POC 通過後再開始。**

## Business / User Goal

`resource_history_service.export_csv()` 目前執行兩次全量 DataFrame（`read_sql_df(detail_sql)` + `read_sql_df(oee_sql)`），無 chunk 保護，是 OOM 風險第 4 名。`resource_dataset_cache.py` 內部的 `iterrows` 迴圈在大量設備資料時效能低落。

`resource_dataset_cache` 已有 base+OEE ThreadPoolExecutor（max_workers=2），是正向參考，遷移至 `BaseChunkedDuckDBJob` 改動相對最小（L 等級但架構清晰）。

## Non-goals

- 不修改前端 resource 相關頁面（spool schema 不變）
- 不遷移 material_trace、downtime

## Constraints

- Feature flag `RESOURCE_HISTORY_USE_UNIFIED_JOB`（預設 `off`）
- `export_csv` 的兩次全量 `read_sql_df` 改為 chunk-to-spool（`decompose_by_time_range`）
- `iterrows` → DuckDB SQL 替換（DuckDB 內聚合，不經 Python 迴圈）
- 內部 base+OEE ThreadPoolExecutor 已是正向參考，遷移時保留並行模型
- OEE 計算涉及跨班加總（cross-row reduction），需確認 chunk 策略是否屬 `requires_cross_chunk_reduction=True`（按 RESOURCEID 分組，不可 row-chunk）

## Known Context

- 架構設計文件：`docs/architecture/query-dataflow-unification.md`（必讀）
- 前置提案：`eap-alarm-unified-job-poc`
- 現有實作：`services/resource_history_service.py`、`services/resource_dataset_cache.py`
- OEE 計算背景：`memory/project_oee_calculation.md`
- cache-spool patterns：`docs/architecture/cache-spool-patterns.md`

## Open Questions

- OEE 的跨班加總是否構成 cross-row aggregation？若是，chunk strategy 應改為按 RESOURCEID 分組（`requires_cross_chunk_reduction=True`），需在 design 階段確認。

## Requested Delivery Date / Priority

P2：可與 `production-reject-history-migration` 並行。
