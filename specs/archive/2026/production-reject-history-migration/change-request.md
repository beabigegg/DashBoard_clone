# Change Request

## Original Request

[P2] Production History 與 Reject History 遷移至 `BaseChunkedDuckDBJob`，移除 pandas 熱路徑並消除 post-hoc OOM 保護點。

**實作前必須完整閱讀 `docs/architecture/query-dataflow-unification.md`，尤其是 §3 遷移計畫 P2 行（production_history_*、reject_history_service.py、reject_dataset_cache.py）。本提案依賴 `eap-alarm-unified-job-poc` POC 通過後再開始。**

## Business / User Goal

- **Production History**：目前 `production_history_routes` 有 RSS sync fallback guard，在 RSS 壓力過高時降同步執行 pandas 查詢，仍阻塞 worker。遷移後統一走 chunk-to-spool，同步降級路徑也不再有大範圍 pandas SELECT。
- **Reject History**：`reject_dataset_cache.py` 多處 `pd.read_parquet()` 讀回全量後才在 Python 側 filter/groupby；`reject_history_service.py` 的 groupby/pareto/trend 均用 pandas，有 6 處 post-hoc OOM 保護點（操作後才檢查）。遷移後改用 in-memory DuckDB SQL，OOM 保護變為前置（DuckDB on-disk spill）。

## Non-goals

- 不修改前端任何頁面（spool schema 不變，view 端點 /summary /pareto /trend /detail 不動）
- 不遷移 resource、material_trace、downtime

## Constraints

- Production History 與 Reject History 各自加 feature flag（`PRODUCTION_HISTORY_USE_UNIFIED_JOB`、`REJECT_HISTORY_USE_UNIFIED_JOB`，預設 `off`），確保逐 domain 可安全回滾
- Reject：`pd.read_parquet()` → in-memory DuckDB；groupby/pareto/trend → DuckDB SQL；移除 6 處 post-hoc guard
- Production：移除 RSS sync fallback 的 pandas 路徑；改走 chunk-to-spool
- 兩個 domain 的 chunk strategy 屬 row-level（無 cross-row aggregation），可安全 `TIME` chunk（符合 §2.3 chunk 策略分類）

## Known Context

- 架構設計文件：`docs/architecture/query-dataflow-unification.md`（必讀）
- 前置提案：`eap-alarm-unified-job-poc`（BaseChunkedDuckDBJob 已驗證）
- 現有實作：`services/production_history_service.py`（及相關 cache）、`services/reject_history_service.py`、`services/reject_dataset_cache.py`
- OOM 風險說明：`docs/architecture/query-dataflow-unification.md §1.4`（reject_dataset_cache 第 5 位）
- cache-spool patterns：`docs/architecture/cache-spool-patterns.md`

## Open Questions

- Production History 是否已有 `merge_chunks_to_spool()` 路徑？需確認現有 parquet+DuckDB 程度再決定改動量。

## Requested Delivery Date / Priority

P2：`eap-alarm-unified-job-poc` POC 通過後，此提案可與 `resource-history-migration` 並行進行。
