# Change Request

## Original Request

[P0] 新增查詢架構統一基礎模組：`BaseChunkedDuckDBJob`、`QueryCostPolicy`、`OracleArrowReader`。

此為整個查詢架構統一遷移計畫的地基，所有後續 P1–P5 提案均依賴此處定義的抽象。

**實作前必須完整閱讀 `docs/architecture/query-dataflow-unification.md`，尤其是 §2 目標架構、§4 核心共用模組設計、§6 第一個實作目標。**

## Business / User Goal

目前 MES Dashboard 存在三條查詢路徑；其中路徑 (C)「慢查詢同步保護」（timeout/semaphore/threading/RSS guard）仍阻塞 gunicorn worker，且所有 OOM 保護機制幾乎都是「操作後才檢查」（post-hoc guard），無法阻止 OOM 實際發生。

本提案建立統一基底，使所有後續 domain 遷移都能以「Oracle 並行 chunk → Arrow → DuckDB → parquet spool」取代 pandas in-memory 路徑，消除 OOM 根因並統一閾值判斷。

## Non-goals

- 不遷移任何現有 domain（eap_alarm、production、reject、resource、material_trace、downtime）
- 不修改任何現有 route 或 service 邏輯
- 不變更前端 spool/view 機制

## Constraints

- `BaseChunkedDuckDBJob` 需支援 `requires_cross_chunk_reduction=False` 路徑（multi-parquet append，規避 DuckDB 單 writer 限制）與 `True` 路徑（DuckDB INSERT + writer_lock）
- `chunk_strategy` 需支援四種：TIME、ID_LIST、ROW_COUNT、SINGLE（設計時期分類，承襲 ADR-0003）
- Oracle connection pool：`min=2, max=12–15`，每 chunk 一條獨立連線，`finally: conn.close()` 歸還
- DuckDB job file 路徑：`{DUCKDB_JOB_DIR}/{namespace}/{job_id}.duckdb`；job 結束後即刪，孤兒由 TTL 清掃
- `classify_query_cost` 四層短路：L0 spool hit → SYNC、L1 always-async domain → ASYNC、L2 date span、L3 rowcount COUNT(*)
- 不引入新的 pip 依賴；使用現有 oracledb、pyarrow、duckdb

## Known Context

- 架構設計文件：`docs/architecture/query-dataflow-unification.md`（必讀）
- ADR-0003（cross-row reduction 不可 row-chunk）：`docs/adr/0003-downtime-rowcount-chunking-exclusion.md`
- 現有 BatchQueryEngine（`services/batch_query_engine.py`）的 `_effective_parallelism()`、`merge_chunks_to_spool()` 為正向參考
- 現有 global concurrency semaphore：`core/global_concurrency.py`（Redis Sorted Set + Lua CAS）
- 現有 progress bracket 模式：coarse 5→15→90→100（`docs/architecture/cache-spool-patterns.md` Type B async 段落）

## Open Questions

- DUCKDB_JOB_DIR 環境變數預設值是否使用 /tmp 還是與 QUERY_SPOOL_DIR 同層？
- Oracle session pool 是全域單例還是每個 worker process 各自持有？

## Requested Delivery Date / Priority

P0：最高優先，所有後續提案的前置條件。建議先行完成再開啟其他提案。
