# Change Request

## Original Request

統一大表查詢機制：BatchQueryEngine → Spool 全面接入 + ROW_NUMBER() CTE row-count 分段取代日期區間分段

## Business / User Goal

1. 所有大量查詢服務統一走 `BatchQueryEngine → merge_chunks_to_spool → Spool Parquet`，消除直接 Oracle → Spool 的路徑不一致
2. 以固定 row 數（`ROW_NUMBER() CTE + rn BETWEEN :start AND :end`）取代固定日期區間（grain_days=31）做 chunk 分段，讓每個 chunk 的記憶體用量更均勻
3. 補齊 hold/job/msd 三個服務的平行化設定（`ENGINE_PARALLEL`）
4. 引入 `USE_ROW_COUNT_CHUNKING` env flag，支援逐服務驗證與 zero-downtime 切換

## Non-goals

- `yield_alert_dataset_cache`：已使用 streaming iterator（最優記憶體路徑），不納入
- `material_trace_service`：ID-set based 分段，已有自己的 spool + streaming 路徑，改寫收益接近零
- `material_consumption_service`：彙總查詢、資料量小，低優先，本 change 不納入
- 前端 UI 無任何改動

## Constraints

- Oracle 12c+（已確認，現有 OFFSET/FETCH 語法已在使用）
- `USE_ROW_COUNT_CHUNKING=false`（預設）→ 保留日期分段路徑為 fallback，不得破壞現有行為
- `DB_SLOW_POOL_SIZE` 限制：production=3, development=2，parallel 不得超過連線池
- 現有 spool TTL、cleanup、memory guard 機制不得變更
- 不得修改 `yield_alert`、`material_trace`、`material_consumption` 三個服務

## Known Context

（來自 2026-06-01 規劃工作階段）

現況盤點：
- 6 個服務已走 BatchQueryEngine → Spool：production_history, reject, resource, hold, job, mid_section_defect
- 2 個服務待接入：downtime_analysis（直接 Oracle → spool），material_consumption（低優先，本 change 排除）
- hold/job/msd 的 ENGINE_PARALLEL 未設定，仍為順序查詢（=1）
- production_history 已有 count_query.sql 可直接複用

各服務 ORDER BY key（ROW_NUMBER() 用）：
- production_history: TRACKINTIMESTAMP ASC, CONTAINERID
- reject_dataset: TXN_DAY DESC, CONTAINERNAME ASC
- resource_dataset: HISTORYID ASC, DATA_DATE ASC
- hold_dataset: HOLDTXNDATE DESC, CONTAINERID ASC
- job_query: CREATEDATE DESC, JOBID ASC
- mid_section_defect: TRACKINTIMESTAMP ASC, CONTAINERID ASC
- downtime_analysis: OLDLASTSTATUSCHANGEDATE DESC, HISTORYID ASC

## Open Questions

（已於規劃工作階段解答，無剩餘問題）

## Requested Delivery Date / Priority

高優先；平行化 .env 設定（Phase 0）可立即部署。
