# Change Request

## Original Request

[P3] Material Trace 遷移：將 `_execute_batched_query` 的 `pd.concat(chunks)` 改為 streaming Arrow → DuckDB，移除 concat 後才檢查的 post-hoc memory guard。

**實作前必須完整閱讀 `docs/architecture/query-dataflow-unification.md`，尤其是 §3 遷移計畫 P3 行（material_trace_service.py）、§1.4 OOM 風險點第 3 名、§2.3 chunk 策略（ID_LIST：decompose_by_ids，1000/批，可並行）。本提案依賴 `eap-alarm-unified-job-poc` POC 通過後再開始。**

## Business / User Goal

`material_trace_service._execute_batched_query()` 目前使用 `pd.concat(chunks)` 把所有 chunk 全量載回記憶體，concat **之後**才呼叫 `_check_memory_guard()`，guard 已太遲無法阻止 OOM（OOM 風險第 3 名）。

同時 `material_trace` 有跨 worker 並行 semaphore（`core/global_concurrency.py`），目前是「保護同步路徑」，遷移後語意轉為「限制 RQ 並行打 Oracle」。

遷移後每個 batch（1000 IDs/批）直接 streaming 到 DuckDB，memory guard 前置為 DuckDB on-disk spill，不再有 post-hoc 記憶體檢查。

## Non-goals

- 不修改前端 material trace 相關頁面（spool schema 不變）
- 不遷移 downtime

## Constraints

- Feature flag `MATERIAL_TRACE_USE_UNIFIED_JOB`（預設 `off`）
- chunk strategy 使用 `ID_LIST`（`decompose_by_ids`，1000/批），ID-list 過大（Oracle IN > 1000）；此模式**可並行**（§2.3）
- 移除 concat 後才呼叫 `_check_memory_guard()` 的後置 guard，改為 DuckDB on-disk spill 前置保護
- `semaphore` 語意從「保護同步」轉為「限制 RQ 並行打 Oracle」（不需程式碼改動，只需更新文件/contract）

## Known Context

- 架構設計文件：`docs/architecture/query-dataflow-unification.md`（必讀）
- 前置提案：`eap-alarm-unified-job-poc`
- 現有實作：`services/material_trace_service.py`、`core/global_concurrency.py`
- 現有 semaphore 機制：`core/global_concurrency.py`（Redis Sorted Set + Lua CAS；`HEAVY_QUERY_MAX_CONCURRENT` 預設 3）

## Open Questions

- material_trace 的最終結果是否有 cross-lot aggregation？若有，需確認是否屬 `requires_cross_chunk_reduction=True`。

## Requested Delivery Date / Priority

P3：P2 兩個提案完成後開始。此提案難度 M（1–2 天），可與 `downtime-duckdb-join-migration` 先行。
