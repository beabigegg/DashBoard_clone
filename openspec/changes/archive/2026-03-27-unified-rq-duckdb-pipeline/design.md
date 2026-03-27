## Context

目前系統已有部分報表走 `dataset_cache -> batch_query_engine -> parquet spool -> *_sql_runtime` 的模式，但整體仍不一致：

- `reject-history`、`yield-alert`、`hold-overview`、`resource-history`、`production-history` 已有不同程度的 spool / DuckDB 能力
- `MSD` staged trace 只有部分 async / spool 能力，detail/export 與舊 `/analysis` 路徑仍會重跑或在 memory 內聚合
- `query-tool trace` 與 `material-trace` 仍以 legacy / in-memory / sync 路徑為主
- warmup 仍由 `cache_updater` 在 gunicorn worker 內執行，而且只覆蓋 reject / yield-alert 的 30 天資料

現況最大的問題，不是方向錯，而是**架構目標已先行，外部契約與資料集識別模型還沒補齊**。如果直接照「所有查詢 spool miss 一律 202」或「前端主流程已不用就刪 endpoint」去做，會破壞現有 API、AI consumer、前端頁面與測試。

## Goals / Non-Goals

**Goals**

- 在同一個 change 內，把非即時重查詢收斂到 RQ→Parquet→DuckDB 的統一架構
- 補齊 canonical dataset identity，讓 spool reuse、detail/export、warmup、polling 都有穩定對應
- 用 compatibility gate 保護既有 API / frontend / AI consumer，不讓架構重整破壞既有功能
- 讓 guard / truncation 的移除有前提，不在 legacy path 尚未退場前過早拆保護

**Non-Goals**

- 不拆成多個 OpenSpec change
- 不在本文件內承諾所有 route 同步改成單一 UX；統一的是後端架構，不是忽略既有 contract
- 不在 canonical dataset identity 尚未設計完成前，先宣告所有報表都能做 90 天 warmup

## Decisions

### D0: 同一 change，使用相容性閘門而非拆提案

**決定**：本 change 保持單一 proposal / design / tasks，但內部所有 capability 以 compatibility gate 控制切換順序。

**原則**

- 已公開或已有 consumer 的 API，先保留 compatibility contract
- consumer migration 與 parity test 未完成前，不刪 route、不改 response envelope、不改前端預期的同步/非同步語意
- 同一 change 可以完成 endpoint retirement，但 retirement 的驗收條件必須明確寫入 tasks

### D1: 統一的是執行模型，不是立刻統一所有外部 response semantics

**決定**：所有重查詢的最終執行模型都收斂到 RQ→Parquet→DuckDB，但外部 route 在 spool miss 時可有兩種合法行為：

1. **compatibility bootstrap**：維持既有同步首屏/首頁 contract
2. **async enqueue**：回 `202 + job_id + status_url`

是否採用哪一種，由該報表現有 contract 與前端遷移狀態決定。

**理由**：目前 `resource-history`、`production-history` 前端都預期 `POST /query` 立即取得資料；強行改成 202 只會破壞已上線頁面。

### D2: Canonical dataset identity 必須逐報表定義

**決定**：本 change 先明確定義每個報表的 canonical spool key，分成三類：

| 報表 | 目前 identity 狀態 | 可否直接 warmup | 本 change 要求 |
|------|--------------------|-----------------|----------------|
| reject-history | 接近 canonical date-range dataset | 可以 | 保持 date-range base dataset，納入 scheduler |
| yield-alert | canonical date-range dataset | 可以 | 納入 scheduler |
| hold-overview | query_id 主要由日期決定 | 可以 | 納入 scheduler |
| resource-history | 目前 query_id 含 filters / flags | 可，但需先重構 | 先抽出 date-range canonical base dataset，filters 改為 DuckDB/view-time predicates；外部 route contract 保持不變後，再納入 scheduler |
| production-history | 目前 query strongly depends on `pj_types` + filters | 不做 | 本 change 不做 warmup / periodic cache，只做 on-demand spool reuse |
| MSD trace | on-demand | 不做全量 warmup | 以 `trace_query_id` 管理 spool |
| query-tool trace | on-demand | 不做全量 warmup | 以 batch query hash 管理 spool |
| material-trace | on-demand | 不做全量 warmup | 以 canonical query hash 管理 spool |

**理由**：沒有穩定 identity，就沒有可靠的 warmup hit、detail/export 命中與 spool reuse。

### D2.1: `resource-history` canonicalization 不應破壞前端契約

**決定**：

- `resource-history` 可以改成「先抓 date-range base dataset，再由 DuckDB/runtime 套用 workcenter/family/resource/flag filters」
- 這個重構只限後端內部 canonical dataset / spool identity 調整
- `POST /api/resource/history/query` 與 `GET /api/resource/history/view` 的 request shape、response envelope、同步 bootstrap 語意維持不變

**理由**：目前 resource 的 filters 主要來自 resource master/cache 維度，而不是 Oracle fact table 不可逆條件，因此可內部下沉到 view/runtime；但既有前端頁面不應被迫跟著改 query 流程。

### D3: MSD 需要正式的 `trace_query_id` / `dataset_id`

**決定**：MSD main query path、detail、export 必須共用同一個 canonical `trace_query_id`。

**要求**

- staged trace main query 完成時，回傳可持久識別 spool 的 `trace_query_id`
- `/analysis/detail` 與 `/export` 優先接受 `trace_query_id`
- 在 compatibility window 內，可保留目前的日期/站別/方向參數，但服務端需先解析到對應的 canonical query，不能靠模糊查找或單純 hash 參數猜測

**理由**：目前前端 detail/export 沒有穩定指向主查詢 spool 的 key，這是設計缺口。

### D4: `/api/mid-section-defect/analysis` 保留為 compatibility adapter，直到消費者清空

**決定**：

- `/api/mid-section-defect/analysis` 在本 change 中**先保留**
- 它的內部實作可改為走 staged / spool / DuckDB 路徑
- `msd_query_job_service.py` 可在 consumer 清理完成後移除，但前提是：
  - frontend 無直接依賴
  - `ai_functions.yaml` 已遷移
  - `contract/api_inventory.md` 已同步
  - route / service / e2e / unit tests 已更新

**理由**：現在它仍在 API inventory、AI registry、測試與舊 spec 承諾內，不能只因「主流程前端已改用 useTraceProgress」就直接刪除。

### D5: Warmup scheduler 必須具 leader lock

**決定**：`spool_warmup_scheduler` 在 app 啟動時可以啟用，但 enqueue warmup job 前必須先取得分散式 lock。

**要求**

- gunicorn 多 worker 啟動時，只允許一個 worker enqueue warmup job
- 週期性 refresh 也必須透過同一把 lock 保證單一 scheduler leader

**理由**：`create_app()` 目前每個 gunicorn worker 都會執行背景初始化；沒有 leader lock 就會重複排程。

### D5.1: `production-history` 在本 change 內不做 warmup

**決定**：

- `production-history` 只要求切到底層 unified spool pipeline
- 不做服務啟動 warmup
- 不做固定間隔週期性 warmup / periodic refresh

**理由**：目前 `production-history` 資料量與 `pj_types` 變異都偏大，先追求安全的 on-demand spool reuse，比先承諾 warmup coverage 更合理。

### D6: RQ pool 隔離沿用現有 `DB_*` 變數，不引入無效別名

**決定**：RQ worker pool 隔離採用實際可生效的方式：

- `database.py` 目前讀的是 `DB_POOL_SIZE` / `DB_MAX_OVERFLOW`
- `start_server.sh` 啟動 RQ worker 時直接注入較小的 `DB_POOL_SIZE=2 DB_MAX_OVERFLOW=1`
- 若要引入 `RQ_DB_*`，必須同時修改 runtime reader；否則文件不得宣告有該設定

**理由**：避免 spec / env.example / runtime 三者不一致。

### D7: hard limit / RSS guard 的移除採「先切 path，再拆 guard」

**決定**：下列 guard 只有在對應查詢確實完成 RQ/spool 遷移後才移除：

- `TRACE_EVENTS_CID_LIMIT`
- `TRACE_SYNC_RSS_REJECT_MB`
- `LINEAGE_MAX_SEED_COUNT`
- `LINEAGE_RSS_REJECT_MB`
- `REJECT_QUERY_RSS_REJECT_MB`
- material trace 的 `_REVERSE_MAX_ROWS` / `_FORWARD_MAX_ROWS` / `_EXPORT_MAX_ROWS`

**理由**：這些 guard 現在是在保護 legacy path；若 path 還沒退場，先拆 guard 只會放大風險。

### D8: EventFetcher / spool writer 以「分 stage 檔案」為主，不假設共享 writer

**決定**：多查詢並行時，優先採用「每個 stage / domain / chunk 先寫自己檔案，最後由 metadata 統一註冊」的模式，不在設計上依賴單一 thread-safe shared ParquetWriter。

**理由**：現有 spool store 已支援 canonical move/register，但沒有成熟的 shared append writer abstraction。用分檔 + DuckDB JOIN 比較符合現有系統能力。

## Migration Rules Inside The Same Change

1. 先補 canonical dataset identity / spool metadata 能力
2. 再補 scheduler leader lock、RQ pool 隔離與 stage-aware progress
3. 再逐報表切到 spool runtime
4. 只有在 parity test、consumer migration、contract update 完成後，才移除 compatibility path 與 guard

這些是**同一個 change 內的遷移規則**，不是拆 proposal。

## Risks / Trade-offs

**[Risk] 單一 change 仍然很大**
Mitigation：在同一 change 內設明確 compatibility gate 與 task dependency，避免邏輯上一步到位、實作上卻互相踩壞。

**[Risk] canonical dataset identity 重新設計會影響 resource / production-history**
Mitigation：resource 在 route contract 不變前提下只改內部 base dataset；production 則先不做 warmup，避免高體量資料在啟動或週期 refresh 時放大風險。

**[Risk] MSD consumer 清理不完全**
Mitigation：把 `/analysis` endpoint retirement 寫成 gated task，不滿足前提就不得刪。

**[Risk] warmup 重複排程**
Mitigation：Redis leader lock + dedicated warmup queue。

## Open Questions

1. `resource-history` 的 canonical base dataset 採較寬 base 後，query_id 對前端是否維持現名或另加內部 dataset_id？
2. `production-history` 的 canonical spool identity 要如何定義，才能在不做 warmup 的前提下仍有良好 reuse？
3. MSD `trace_query_id` 要由前端顯式傳遞，還是由 summary response / session cache 隱式保存？
