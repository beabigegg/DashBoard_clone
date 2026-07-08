# Change Request

## Original Request

生產達成率 (production-achievement) 頁面的查詢發生 Oracle 逾時錯誤（DPY-4024, call timeout 55000ms）。經調查後決定：既然是查詢本身太重的問題，乾脆將此頁改為 **RQ job → DuckDB parquet spool → 前端 DuckDB-WASM 客戶端聚合** 的非同步架構（比照 resource_history）。因功能尚未正式上線，採乾淨取代，不保留同步 fallback 雙軌。使用 CDD 起案。

## Business / User Goal

工程師查詢生產達成率報表時不再因後端 Oracle 查詢逾時而失敗；重量級 DWH 查詢移出 HTTP 請求路徑，改由背景 RQ worker 產出 SPECNAME 粒度的 DuckDB parquet spool，前端下載後在 DuckDB-WASM 內完成 workcenter_group rollup、target join 與達成率計算。

**Observable success criterion:** 一次 30 天（以及最大 730 天）的 production-achievement 報表請求不再觸發 DPY-4024 逾時（請求路徑上的 Oracle 查詢被消除）；前端渲染的列（output_date, shift_code, workcenter_group, actual_output_qty, target_qty, achievement_rate）在相同日期範圍下與現行同步實作結果一致。

## Non-goals

- 不優化 sql/production_achievement.sql 的 PA-05 資格判定邏輯（WORKFLOWNAME 橋接、SPECNAME/processtypename 分支）本身 — 原樣搬進 chunk SQL。
- 不改變 PA-01..PA-07 的業務語意（班別、output_date、達成率公式），僅改變 PA-06/PA-07 的**計算執行位置**（後端 Python → 前端 DuckDB-WASM）。
- 不保留同步 `/report` 回舊行為的雙軌路徑；不引入 `*_USE_RQ` 灰度 flag（採 always_async）。
- 不動 targets 編輯（PUT）與權限相關端點的行為。

## Constraints

- 功能尚未正式上線 → 可乾淨取代同步端點，不需向後相容。
- 必須沿用既有機制、不自創：BaseChunkedDuckDBJob、query_spool_store、async_query_job_service、spool_routes、前端 core/duckdb-client.ts + useAsyncJobPolling。
- gunicorn↔RQ worker 的 feature-flag/env 必須 parity（env-contract §Worker Feature-Flag Env-Var Parity）。
- 新 worker 必須加入 tests/test_query_cost_policy.py 的 `_APPROVED_CALLERS`；spool namespace 必須加入 spool_routes._ALLOWED_NAMESPACES（同一 PR）。
- parquet schema 需帶 `_SCHEMA_VERSION`；schema break 時 rollback runbook 要加 `rm` 並同 commit bump 版本。

## Known Context

- 根因：`production_achievement_service.get_achievement_report()` 走 `read_sql_df`（55s 快速池 call_timeout），是全專案唯一還掛在快速池的重量級 DWH 分析查詢；其餘同級查詢皆走 `read_sql_df_slow` 或非同步 spool。commit a68d9ba4 (#21) 的橋接修復只把 30 天窗口降到 ~22-32s，餘裕不足，資料成長後再度突破 55s。
- 現行後端 `build_achievement_rows()` 做 SPECNAME→workcenter_group rollup（PA-06，via filter_cache.get_spec_workcenter_mapping）+ targets join + achievement_rate（PA-07）— 這段要移到前端 DuckDB-WASM。
- 參考實作：resource_history（option A：瀏覽器直接下載 parquet 進 DuckDB-WASM）— worker `resource_history_base_worker.py`、`resource_dataset_cache.py`、route `_inject_resource_spool_info`、前端 `useResourceHistoryDuckDB.ts`。
- 前端 activation policy（duckdb-activation-policy.ts）門檻預設 5000 列；PA SPECNAME 粒度結果可能不足 5000 列。

## Open Questions

- **Q1（design 需拍板）**：前端 `checkLocalComputeEligibility` 的 5000 列門檻，PA 結果集可能低於門檻。選項：(a) 為此頁降低/覆寫門檻讓 DuckDB-WASM 一律啟用；(b) 保留一條 server-side DuckDB 聚合 fallback（比照 production_history option B 的 `/view` 讀 spool）。
- **Q2**：targets map 與 spec→workcenter_group mapping 送到前端的載體 — 隨 job 完成回應內嵌，或前端另打既有的 `/filter-options`、`/targets` 端點取得後在前端 join。
- **Q3**：spool 交付採 option A（瀏覽器下載 parquet）還是 option B（server-side DuckDB 讀 spool）；預設 option A，但與 Q1 連動。

## Requested Delivery Date / Priority

高（現行頁面查詢在生產環境已逾時失敗）。此功能尚未正式上線，無回歸上線用戶風險，但需盡快恢復可用。
