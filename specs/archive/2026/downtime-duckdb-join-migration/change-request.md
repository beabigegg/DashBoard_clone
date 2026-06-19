# Change Request

## Original Request

[P3] Downtime Analysis 遷移：將 `_bridge_jobid` Path B 的 N×M Cartesian join（`pd.merge`）改為在 DuckDB 內執行 JOIN，消除系統中最高 OOM 風險點，同時保持「不可 row-chunk」分類（按 RESOURCEID 分組）。

**實作前必須完整閱讀 `docs/architecture/query-dataflow-unification.md`，尤其是 §3 遷移計畫 P3 行（downtime_analysis_service.py，難度 XL）、§1.4 OOM 風險點第 1 名、§2.3 chunk 策略（cross-row aggregation 不可 row-chunk，按 RESOURCEID 分組）。同時必須閱讀 `docs/adr/0003-downtime-rowcount-chunking-exclusion.md`。本提案依賴 `eap-alarm-unified-job-poc` POC 通過後再開始。**

## Business / User Goal

`downtime_analysis_service._bridge_jobid()` Path B 使用 `pd.merge(events_b, jobs_b, how='left')`，這是 RESOURCEID × 時間重疊的 N×M Cartesian 前置 join，ADR-0003 已排除 row chunking，**目前無任何 chunk 保護**，是全系統最高 OOM 風險點。

遷移後將 events 與 jobs 兩份資料分別以 streaming Arrow 寫入 DuckDB（兩張表），再在 DuckDB 內執行 JOIN，利用 DuckDB 的 on-disk spill 避免 Python heap OOM。chunk 維度改為按 RESOURCEID 分組（每個 RESOURCEID 獨立 job chunk），符合 ADR-0003 的「不可 row-chunk，但可按獨立鍵分組」原則。

## Non-goals

- 不修改前端 downtime 相關頁面（spool schema 不變）
- 不變更 ADR-0003 的核心決策（cross-row aggregation 不可 row-chunk）

## Constraints

- Feature flag `DOWNTIME_USE_UNIFIED_JOB`（預設 `off`）
- chunk strategy：按 RESOURCEID 分組（`requires_cross_chunk_reduction=True`，`chunk_strategy=SINGLE` per group）；**不可**使用 `TIME` 或 `ROW_COUNT` chunking（ADR-0003）
- `_bridge_jobid` Path B 的 `pd.merge` 必須完全移除，改為 DuckDB JOIN（DuckDB 處理時間重疊比對）
- 此提案難度 XL（> 1 週），需獨立 design.md 說明 RESOURCEID 分組模型與 DuckDB JOIN 策略
- 需與 `reference_mes_downtime_job_tables.md`（JOBID 近期覆蓋崩壞，改用 RESOURCEID+時間重疊橋接）保持一致

## Known Context

- 架構設計文件：`docs/architecture/query-dataflow-unification.md`（必讀）
- ADR-0003：`docs/adr/0003-downtime-rowcount-chunking-exclusion.md`（必讀）
- 前置提案：`eap-alarm-unified-job-poc`
- 現有實作：`services/downtime_analysis_service.py`
- MES 停機資料模型：`memory/reference_mes_downtime_job_tables.md`（JOBID 橋接邏輯）
- 現有 service-patterns：`docs/architecture/service-patterns.md`（`downtime_analysis_service` 段落）

## Open Questions

- DuckDB 內的時間重疊 JOIN 是否需要 window function？需在 design 階段確認 SQL 策略。
- RESOURCEID 分組的粒度：一個 job = 一個 RESOURCEID，還是支援多 RESOURCEID 批次？

## Requested Delivery Date / Priority

P3（XL）：難度最高，建議獨立排程，預估 > 1 週。可與 `material-trace-streaming-migration` 先行但不必等待。
