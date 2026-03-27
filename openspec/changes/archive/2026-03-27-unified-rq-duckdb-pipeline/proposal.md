## Why

所有非即時報表（reject-history、yield-alert、resource-history、hold-overview、production-history、MSD 中段不良追溯、query-tool trace、material-trace）的重查詢，現在仍混用多套執行模型，導致三個結構性問題：

1. **OOM / 高 RSS 風險**：部分查詢仍在 gunicorn worker 內做大結果集聚合，資料量一大就會把 worker RSS 推高，造成 MemoryError、503 或系統級 OOM。
2. **保護性硬限制傷害可用性**：CID 限制、seed 限制、MAX_ROWS 截斷、RSS guard 等措施雖然保護了服務，但也讓使用者在大查詢時被拒絕、被截斷，拿不到完整資料。
3. **快取與 spool 策略分裂**：目前已有部分報表走 parquet spool + DuckDB，但 warmup、async、detail/export、trace aggregation、material trace 仍各自實作，維護成本高，也容易出現同資料重查 Oracle。

## What Changes

### 核心目標

本 change 仍維持單一整體目標：把所有非即時重查詢收斂到 **RQ worker → Parquet spool → DuckDB runtime** 的統一架構。

- Oracle 重查詢在 RQ worker 執行，結果以 streaming 方式寫入 parquet spool，不在 gunicorn worker 內累積大 DataFrame。
- 後續聚合、分頁、排序、匯出，盡量由 DuckDB 直接讀 parquet 完成。
- 現有因 in-memory 路徑而存在的硬限制，會在對應查詢確實完成 spool 化之後再逐步移除。

### 單一提案，但保留相容性閘門

這份提案**不拆成多個 change**，但會在同一 change 內定義明確的相容性閘門，避免開發中途把既有路由、前端或 AI consumer 做壞：

- **既有 API contract 先保留**：已被前端、AI function registry、測試或契約檔使用的 endpoint，不會僅因「主流程已改走 staged API」就直接刪除。
- **相容 adapter 優先**：如 `/api/mid-section-defect/analysis`，會先改成 compatibility adapter 或 deprecated path，直到所有 consumer 完成切換、測試補齊、契約同步後，才允許真正移除。
- **不同報表可保留不同外部交互**：統一的是後端執行模型，不強迫所有 route 在 spool miss 時都立即改成 `202 + polling`。是否同步回首屏、或改為 polling，由該報表既有 contract 與前端遷移狀態決定。

### Canonical spool identity

這個 change 會補齊每種報表的 **canonical dataset / spool identity**，明確定義：

- 哪些報表已經有穩定的 warmup key，可直接做 90 天預載
- 哪些報表目前的 query identity 仍綁定使用者 filters，必須先 canonicalize base dataset，才能安全 warmup
- MSD / trace / material-trace / query-tool 這類 on-demand 查詢，要如何用 `dataset_id` / `query_id` / `job_id` 穩定對應 detail/export/spool reuse

### Warmup 與 scheduler

- 啟動時與固定間隔會透過 RQ enqueue warmup job，但 scheduler 必須具備 **distributed lock / leader election**，避免每個 gunicorn worker 都重複排一次 job。
- warmup 只會針對**已定義 canonical warmup key** 的報表啟用。
- reject / yield-alert / hold 這類已接近 canonical dataset 的報表可優先納入。
- resource-history 會在同一 change 內改成較寬的 canonical base dataset，再由 DuckDB/runtime 套用既有 filters；這個調整以**前端 route contract 不變**為前提。
- production-history 因資料量與 `pj_types` 變異較大，在本 change 內**不納入啟動 warmup 或週期性 warmup**；僅收斂到底層 unified spool pipeline，按需查詢與 reuse spool。

### MSD / trace / material-trace

- MSD staged trace 的 events aggregation、detail、export 會改成 spool + DuckDB 路徑，但會先補齊穩定的 `trace_query_id` / `dataset_id` 對應模型。
- `/api/mid-section-defect/analysis` 不再作為主要新功能路徑，但在 consumer 清理完成前保留 compatibility contract。
- material-trace 會朝 RQ + spool + DuckDB 遷移，並在前後端同時補上 async/polling 能力後，才切成 `202` 路徑。

## Capabilities

### New Capabilities

- `unified-spool-pipeline`: 統一的 RQ→Parquet→DuckDB pipeline 框架，定義共用的 job enqueue、stage spool、DuckDB runtime 介面與 canonical dataset identity
- `spool-warmup-scheduler`: 啟動時 + 定期 enqueue 的 warmup 排程機制，具 leader lock，僅 warmup 已 canonicalize 的報表
- `rq-connection-pool-isolation`: RQ worker 使用獨立且較小的 Oracle pool，避免搶占 gunicorn 連線

### Modified Capabilities

- `trace-staged-api`: events stage 改以 spool / RQ 為主；硬限制只在 legacy sync path 未退場前保留，完成切換後移除
- `msd-lineage-spool`: MSD lineage / events / aggregation 納入統一 spool identity 與 DuckDB runtime
- `msd-async-analysis`: `/api/mid-section-defect/analysis` 改為 compatibility-first 策略；detail/export 改從 spool 讀取，但 endpoint 移除必須以 consumer migration 為前提
- `lineage-admission-control`: seed count / RSS guard 的移除以 lineage 全面切到 RQ spool path 為前提
- `event-fetcher-unified`: row truncate guard 的移除以 caller 已完成 spool 化為前提
- `reject-query-backpressure`: reject async / spool / warmup 納入統一 pipeline，但不先破壞現有 response contract
- `material-trace-api`: material trace 改為 spool + DuckDB + async capable；前端 polling 契約與匯出契約需一併完成
- `dataset-cache-warmup`: 現有 dataset warmup 從 cache_updater 遷移到 RQ scheduler，但會以 canonical warmup coverage 為準
- `parquet-spool-view-engine`: 擴展現有 spool store，支援多 stage 檔案、namespace file listing、canonical query lookup
- `async-query-job-service`: 統一所有 RQ job 的 enqueue/status/progress 介面，支援 stage-aware progress

## Impact

### 後端

- 擴展 `query_spool_store.py`、新增 `spool_pipeline.py`、`spool_warmup_scheduler.py`
- 調整 `trace_routes.py`、`trace_job_service.py`、`event_fetcher.py`、`lineage_engine.py`、`material_trace_service.py`
- 對 MSD 補上穩定的 spool dataset identity 與 DuckDB runtime
- 保留既有 compatibility endpoint，直到 AI / frontend / tests / contract 全部遷移完成

### 前端

- resource-history 改為 canonical base dataset 屬於後端內部資料集重整；只要 `POST /query`、`GET /view`、`query_id` / response envelope 不變，既有前端頁面無須改版
- 需要補齊使用 async/polling 的頁面與 composable，但只在對應 API contract 一起切換時變更
- 不再假設「所有報表同一天都改成 202」，而是以該報表的 route contract 遷移完成為切換點

### 基礎設施

- spool 容量、TTL、RQ worker pool 會重新整理為一致命名與實際可生效的設定
- warmup 排程會新增 leader lock，避免 gunicorn 多 worker 重複 enqueue

## Guardrails

- 不以「前端主流程目前沒在 call」作為刪除 API 的唯一依據
- 不以「最終想統一 polling」作為立刻改壞現有 route contract 的理由
- 不在 canonical dataset identity 尚未成立前，宣告某報表可直接做 90 天 warmup
- 不在 legacy sync path 尚未退場前，先移除保護系統穩定性的 guard
