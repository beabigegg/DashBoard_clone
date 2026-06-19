# Change Request

## Original Request

[P1] EAP Alarm POC：將 `eap_alarm_worker` 重構為繼承 `BaseChunkedDuckDBJob`，同時統一 `job_registry` enqueue 入口，消除 Pattern A/B 分裂。

**實作前必須完整閱讀 `docs/architecture/query-dataflow-unification.md`，尤其是 §3 遷移計畫 P1 行、§6 第一個實作目標（POC 選擇：eap_alarm）。本提案依賴 `unified-query-core-infra` 完成。**

## Business / User Goal

eap_alarm 是最接近目標架構 80% 的 domain（零 pandas、Oracle → parquet → in-memory DuckDB SQL view），將它作為 POC 可以驗證 `BaseChunkedDuckDBJob` 基底的正確性，同時示範 `decompose_by_time_range` + ThreadPoolExecutor 並行帶來的查詢加速。

目前 `run_eap_alarm_query_job` 兩次 `read_sql_df_slow` 是序列查詢，Oracle IN > 999 才用 OR clause 拆解，未使用 chunk 並行。遷移後跨 90 天查詢的 wall-time 應明顯下降，記憶體峰值不隨資料量線性上升。

統一 enqueue 入口，消除 Pattern A（`enqueue_job_dynamic` + registry `should_enqueue`）與 Pattern B（各自建 `enqueue_xxx` 直呼 `enqueue_job`）的分裂，加入 `sync_fallback_allowed` / `always_async` flag。

## Non-goals

- 不修改前端 eap_alarm 相關頁面（view 端已是 in-memory DuckDB，spool schema 不變）
- 不遷移其他 domain（production/reject/resource/material_trace/downtime）
- 不變更現有 spool parquet schema

## Constraints

- `EapAlarmJob` 繼承 `BaseChunkedDuckDBJob`（來自 `unified-query-core-infra`）
- eap_alarm 為 `always_async=True`，chunk strategy 使用 `TIME`，`requires_cross_chunk_reduction=False`（row-level alarm，無 cross-row reduction，不踩 ADR-0003）
- Feature flag `EAP_ALARM_USE_UNIFIED_JOB`（預設 `off`），route enqueue 依 flag 選新/舊 worker_fn
- 新路徑產出的 spool parquet 與舊路徑 schema + rowcount 必須等價（驗收標準）
- Oracle 連線 `finally: conn.close()` 歸還，無洩漏

## Known Context

- 架構設計文件：`docs/architecture/query-dataflow-unification.md`（必讀）
- 前置提案：`unified-query-core-infra`（`BaseChunkedDuckDBJob`、`OracleArrowReader` 必須先完成）
- 現有實作：`workers/eap_alarm_worker.py`、`services/eap_alarm_service.py`、`routes/eap_alarm_routes.py`
- 現有 job registry：`services/job_registry.py`、`services/async_query_job_service.py`
- 現有測試：`tests/test_eap_alarm_service.py`（需擴充：新舊路徑等價、chunk 並行無重複/遺漏、progress bracket、連線無洩漏）

## Open Questions

- `job_registry` 統一入口的 `sync_fallback_allowed` flag 對 always_async domain（eap_alarm）的實際行為：降同步是否應直接 503？

## Requested Delivery Date / Priority

P1：前置 `unified-query-core-infra` 完成後立即開始。此 POC 通過是 P2 以後所有 domain 遷移的信心基礎。
