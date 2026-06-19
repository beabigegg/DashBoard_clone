# Change Request

## Original Request

[P4+P5] 消除路徑 (C) 最後殘留並清理散落 env：`query_tool_routes` 超閾值改 enqueue RQ、`wip_routes` 加 rowcount 預檢、`batch_query_engine.merge_chunks` 標記 deprecated、移除各 route 的 `*_ASYNC_DAY_THRESHOLD` env。

**實作前必須完整閱讀 `docs/architecture/query-dataflow-unification.md`，尤其是 §3 遷移計畫 P4/P5 行、§1.1 路徑(C)定義（慢查詢同步保護，目標是消除）、§2.2 classify_query_cost（統一閾值政策）。本提案依賴 `unified-query-core-infra`（`query_cost_policy.py`）完成。**

## Business / User Goal

完成路徑 (C) 消除的最後一哩：

- **P4 `query_tool_routes`**：目前 `@map_service_errors` 同步等待 `QueryTimeoutError`（300s），超時才轉 HTTP 錯誤，整段期間 gunicorn worker 被阻塞。改為超過 `classify_query_cost` 閾值即 enqueue RQ，回 202+job_id。
- **P4 `wip_routes`**：即時 WIP 多為小查詢（影響面小），但超大查詢時仍有阻塞風險。加 rowcount 預檢，超大查詢路由到 RQ。
- **P5 `batch_query_engine.merge_chunks`**：`pd.concat(dfs)` 把所有 chunk 全量載回記憶體，是 OOM 第 2 名。標記 `@deprecated`，新增 docstring 明確禁止新 caller 使用，現有 caller 已逐步由 P1–P3 遷移至 `merge_chunks_to_spool()`。
- **P5 env 清理**：各 route 的 `*_ASYNC_DAY_THRESHOLD` env（7 個）移除，統一讀 `query_cost_policy.py` 的 `CostPolicy` 設定，清理 `.env.example` 與相關文件。
- **global_concurrency semaphore 語意更新**：從「保護同步路徑」改為「限制 RQ 並行打 Oracle」，更新 contract 文件。

## Non-goals

- 不遷移任何 domain service（由 P1–P3 負責）
- 不刪除 `batch_query_engine.py`（只標記 deprecated，等所有 caller 遷移完畢再刪）

## Constraints

- `query_tool_routes` 改動需加 feature flag `QUERY_TOOL_USE_RQ`（預設 `off`），確保回滾
- `wip_routes` rowcount 預檢閾值使用 `classify_query_cost` 的 L3（200,000 行）；WIP 即時查詢多小，此 flag 影響面小
- `merge_chunks` deprecated 標記不可破壞現有 caller（backward compatible）；僅新增 `DeprecationWarning` + docstring
- env 清理需同步更新 `.env.example`、contracts 中相關文件、CI 環境設定

## Known Context

- 架構設計文件：`docs/architecture/query-dataflow-unification.md`（必讀）
- 前置提案：`unified-query-core-infra`（`query_cost_policy.py` 必須先完成）
- 現有實作：`routes/query_tool_routes.py`、`routes/wip_routes.py`、`services/batch_query_engine.py`、`core/global_concurrency.py`
- 散落 env 清單：`QUERY_TOOL_ASYNC_DAY_THRESHOLD`、`WIP_ASYNC_DAY_THRESHOLD` 等 7 個（需掃描確認完整清單）

## Open Questions

- `query_tool_routes` 的 RQ job type 是否需新建，還是複用現有 generic heavy job？
- env 清理是否需要 migration guide 或 breaking change notice？

## Requested Delivery Date / Priority

P4+P5（收尾）：P1–P3 所有 domain 遷移完成後執行，是整個遷移計畫的最終清理。
