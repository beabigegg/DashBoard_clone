# 查詢架構統一設計：RQ + DuckDB 取代慢查詢同步保護

> 產生日期：2026-06-18  
> 分析方式：多代理 workflow（4 個掃描 agent + Opus 綜合）  
> 狀態：設計完成，等待實作

---

## 1. 現況摘要（Current State）

### 1.1 三條查詢路徑的界定

目前實際存在三條路徑，目標是保留前兩條、消除第三條：

| 路徑 | 定義 | 觸發判斷 | 代表案例 | 目標 |
|---|---|---|---|---|
| **(A) 一般同步查詢** | 同步打 Oracle、低延遲，或讀 Redis/spool cache | 預設路徑；filter-options、count、view、即時 WIP | `wip_routes` 全部、各 `/options` `/view` `/summary` | ✅ 保留 |
| **(B) RQ 非同步查詢** | 派發 RQ job、回 202+job_id、前端輪詢、結果落 Parquet spool | `enqueue_job` / `enqueue_job_dynamic`；date span ≥ 閾值或 spool miss | eap-alarm、trace、reject、yield-alert、production-history | ✅ 保留並擴大 |
| **(C) 慢查詢同步保護** | 同步等待但加 timeout / semaphore / threading / RSS guard，**仍阻塞 gunicorn worker** | 散落在 service 與 core 層，非統一管理 | `query_tool_routes` timeout、`material_trace` semaphore、`downtime` RSS fallback | ❌ 消除 |

**問題核心**：路徑 (C) 是「假非同步」——它仍然同步阻塞 gunicorn worker，只是用 timeout 或並行限制避免拖垮系統。目標是把所有 (C) 的觸發點改為「超閾值即 enqueue RQ」，讓系統只剩 (A) 純快 + (B) 純 RQ 兩態。

### 1.2 資料流示意圖（現況）

```
                                ┌──────────────────────────────────────────┐
                                │            Oracle (MES 主資料來源)          │
                                └───────────────┬──────────────────────────┘
            ┌───────────────────────────────────┼────────────────────────────┐
            │ (A) SYNC                           │ (B) RQ ASYNC               │ (C) SYNC-GUARDED
            ▼                                    ▼                            ▼
 ┌──────────────────────┐       ┌────────────────────────────┐  ┌───────────────────────────┐
 │ read_sql_df / COUNT  │       │  RQ enqueue → worker        │  │ read_sql_df_slow(300s)     │
 │  (直接同步)           │       │  ┌──────────────────────┐  │  │  + heavy_query_semaphore   │
 │  └─► Redis L1/L2     │       │  │ execute_primary_query │  │  │  + ThreadPoolExecutor(≤3)  │
 └──────────┬───────────┘       │  └────────┬─────────────┘  │  │  + RSS/Memory guard        │
            │                   │           ▼                 │  └──────────┬────────────────┘
            │                   │  pandas DataFrame ──────┐   │             │ (阻塞 gunicorn)
            │                   │  或 pyarrow streaming   ▼   │             ▼
            │                   │  merge_chunks_to_spool      │   pandas in-memory（OOM 風險）
            │                   │  Parquet spool（磁碟）        │             │
            │                   │  + Redis meta pointer        │             ▼
            │                   └──────────┬──────────────────┘   直接回 JSON / streaming CSV
            │                              ▼
            │                  ┌───────────────────────────┐
            │                  │ in-memory DuckDB           │
            │                  │ read_parquet(spool) → SQL  │  ← eap_alarm 模式（零 pandas）
            │                  └───────────┬───────────────┘
            ▼                              ▼
      ┌──────────────────────────────────────────────────────┐
      │  前端：直接 JSON  |  輪詢 job status → /view → JSON   │
      └──────────────────────────────────────────────────────┘
```

### 1.3 路徑 (B) 內部不一致

目前 RQ 路徑有三種不同的實作模式，混雜在各 domain 中：

| 模式 | 使用 domain | 特徵 |
|---|---|---|
| **Pattern A** | hold, resource, downtime | `enqueue_job_dynamic` + registry `should_enqueue`；失敗靜默降同步 |
| **Pattern B** | reject, production, yield, msd | 各自建 `enqueue_xxx` 直呼 `enqueue_job`；失敗直接 503 |
| **孤立案例** | eap_alarm, trace | 自備 meta wrapper；eap 在 `workers/`，trace 自備 |

觸發判斷也不統一：hold/resource 用 90 天閾值；downtime 用 30 天；reject/production/yield 用 spool miss；trace/eap 永遠 async。

### 1.4 最嚴重 OOM 風險點（按嚴重度排序）

1. **`downtime_analysis_service._bridge_jobid()` Path B** — `pd.merge(events_b, jobs_b, how='left')` 是 RESOURCEID×時間重疊的 N×M Cartesian 前置 join，ADR-0003 已排除 row chunking，**無任何 chunk 保護**
2. **`batch_query_engine.merge_chunks()`** — `pd.concat(dfs)` 把所有 chunk 全量載回記憶體；`merge_chunks_to_spool()` 替代品存在但非所有 caller 採用
3. **`material_trace_service._execute_batched_query()`** — `pd.concat(chunks)` 在 concat **之後**才呼叫 `_check_memory_guard()`，guard 已太遲
4. **`resource_history_service.export_csv()`** — `read_sql_df(detail_sql)` + `read_sql_df(oee_sql)` 兩次全量 DataFrame，無 chunk
5. **`reject_dataset_cache` 多處 `pd.read_parquet()`** — 讀回全量後在 Python 側 filter/groupby，guard 在操作後觸發

**共通病根**：記憶體保護幾乎都是「操作後才檢查」（post-hoc guard），無法阻止 OOM 發生。真正的解法是讓資料**從不進 Python heap**。

### 1.5 目前慢查詢保護機制清單

| 機制類型 | 檔案 | 具體做法 |
|---|---|---|
| 跨 worker 並行 semaphore | `core/global_concurrency.py` | Redis Sorted Set + Lua CAS；`HEAVY_QUERY_MAX_CONCURRENT`（預設 3） |
| process-local ThreadPool cap | `services/batch_query_engine.py` L423–444 | `_effective_parallelism()` 失敗降 1；hard cap `min(requested, 3)` |
| per-chunk 記憶體丟棄 | `batch_query_engine.py` L472–480 | chunk > `BATCH_CHUNK_MAX_MEMORY_MB`（192MB）整個丟棄 |
| 慢查詢 timeout | `read_sql_df_slow`（300s） | 超時拋 `QueryTimeoutError` |
| timeout → HTTP 映射 | `query_tool_routes.py` `@map_service_errors` | `QueryTimeoutError → query_timeout_error()`，仍同步等待 |
| RSS / async fallback guard | `production_history_routes` / `heavy_query_telemetry` | RSS guard 致非同步降級；OOM guard；overload 拒絕 |
| dataset 記憶體護欄 | `material_trace_service._check_memory_guard()` | 操作後檢查，超標拋錯 |
| 內部 ThreadPoolExecutor | `resource_dataset_cache`（base+OEE, max_workers=2）；`trace_job_service`（per-domain, max_workers=2） | 已在 RQ 內並行，是正向參考 |

---

## 2. 目標架構（Target Architecture）

### 2.1 兩層路徑設計

```
                   ┌─────────────────────────────────────┐
POST /api/<f>/query │  Unified Query Dispatcher (route 層)  │
───────────────────►│  classify_query_cost(params)         │
                   └──────────────┬──────────────────────┘
          ┌───────────────────────┴────────────────────────┐
          │                                                 │
  cost < THRESHOLD                                  cost ≥ THRESHOLD
  AND spool/cache hit                               OR spool miss
          │                                                 │
          ▼                                                 ▼
┌────────────────────┐                     ┌──────────────────────────────┐
│ (A) SYNC PATH       │                     │ (B) RQ PATH                   │
│ 1. spool/cache hit  │                     │ 1. classify_query_cost → ASYNC│
│    → in-memory      │                     │ 2. enqueue_job_dynamic(...)   │
│      DuckDB SQL     │                     │ 3. 回 202 + job_id + query_id │
│    → JSON           │                     │ 4. worker:                    │
│ 2. tiny live query  │                     │    BaseChunkedDuckDBJob.run() │
│    (count/options)  │                     │    → chunk → Arrow → DuckDB   │
└────────────────────┘                     │    → post_aggregate → spool   │
                                           │ 5. 前端輪詢 → /view (DuckDB)  │
                                           └──────────────────────────────┘
```

**設計原則：**
- **(A) Sync 只做兩件事**：① 讀已存在的 spool/cache（in-memory DuckDB 在 parquet 上跑 SQL）；② 極輕量 live 查詢（COUNT、filter-options、即時 WIP）。**Sync path 絕不做大範圍 Oracle SELECT 進 pandas**。
- **(B) RQ 接管所有「重」工作**：任何 spool miss + 成本超閾值的 primary query 全部 enqueue，worker 內統一走 chunk → Arrow → DuckDB → spool。
- **降級政策統一**：預設靜默降同步（enqueue 失敗），但同步降級路徑也必須走 chunk-to-DuckDB。eap/trace 這類本質重的維持 always-async + 503。

### 2.2 閾值統一：`classify_query_cost(domain, params)`

新增 `core/query_cost_policy.py`，三道判斷由上而下短路：

| 判斷層 | 規則 | 預設值 | 說明 |
|---|---|---|---|
| **L0** spool/cache hit | 對應 `query_id` 的 spool 存在且未過期 | — | 永遠 SYNC |
| **L1** always-async domain | domain 在 `_ALWAYS_ASYNC` 集合 | trace, eap_alarm, msd | 永遠 ASYNC |
| **L2** date span | `(end - start).days ≥ DAY_THRESHOLD` | 通用 30 天；resource/hold 90 天 | 粗估 |
| **L3** estimated rowcount | 先跑輕量 `COUNT(*)`，`rows ≥ ROW_THRESHOLD` | 200,000 行 | 精準，優先於 L2 |

每 domain 一筆 `CostPolicy(always_async, day_threshold, row_threshold, row_count_fn)`，取代目前散落在 7 個 route 檔的 `*_ASYNC_DAY_THRESHOLD` env。

### 2.3 RQ Job 分段 + 並行設計

核心：複用 `BatchQueryEngine` 的 decompose 能力，但並行模型改為 worker 內 ThreadPoolExecutor 同時打 Oracle，結果各自 streaming 寫入同一個 DuckDB file（不經 pandas concat）。

```
BaseChunkedDuckDBJob.run(job_id, params):
  1. pre_query(params)                          # 解析 filter、決定 chunk 維度
  2. chunks = decompose(params)                 # 時間 / id / row_count 三選一
  3. duckdb_path = open_job_duckdb(job_id)      # 每個 job 一個 .duckdb 檔
  4. with ThreadPoolExecutor(max_workers=K):    # K = effective_parallelism
       for chunk in chunks:
         submit(_fetch_chunk_to_arrow, chunk)   # 各自一條 Oracle 連線 → Arrow RecordBatch
     as_completed:
       writer_lock.acquire()                    # DuckDB 單 writer（C++ 層，快速）
       conn.execute("INSERT INTO raw SELECT * FROM arrow_batch")
       update_job_progress(pct=...)             # coarse bracket per chunk
  5. post_aggregate(conn)                       # DuckDB 內 GROUP BY / JOIN → 最終結果
  6. COPY (SELECT ...) TO 'spool.parquet'       # 落 canonical spool + Redis meta
  7. complete_job(query_id)
  8. _cleanup_job_duckdb(job_id)               # 成功後刪 .duckdb（canonical parquet 已落）
```

**chunk 策略分類（design-time，承襲 ADR-0003）：**

| 查詢型態 | chunk 維度 | 可並行？ | 範例 |
|---|---|---|---|
| 純 row-level（無 cross-row reduction） | `decompose_by_time_range` 或 `decompose_by_row_count` | ✅ 是 | reject, production_history, eap_alarm, resource detail |
| ID-list 過大（Oracle IN > 1000） | `decompose_by_ids`（1000/批） | ✅ 是 | trace events、material_trace |
| cross-row aggregation（cumsum / 跨班 merge / 時數加總） | **不可 row chunk**；按獨立鍵（如 RESOURCEID）分組 | ⚠️ 僅可按 group key 分 | downtime（ADR-0003 排除）、hold future-hold 累計 |

### 2.4 DuckDB 角色：兩層分離

| 層 | 路徑命名 | 生命週期 | 用途 |
|---|---|---|---|
| **Job 暫存 DuckDB** | `{DUCKDB_JOB_DIR}/{namespace}/{job_id}.duckdb` | job 結束後即刪；孤兒由 TTL 清掃 | 接收多 chunk INSERT、GROUP BY/JOIN 聚合，DuckDB on-disk spill 避免 OOM |
| **Canonical Parquet spool** | `{QUERY_SPOOL_DIR}/{namespace}/{query_id}.parquet`（不變） | TTL 由 `query_spool_store` 管（現有） | 前端 view 讀取來源；可跨 job 復用 |

**`requires_cross_chunk_reduction` 旗標：**
- `True`（reject/downtime/yield）→ 開 `{job_id}.duckdb`，所有 chunk `INSERT INTO raw`，`post_aggregate` 在 raw 上 GROUP BY，COPY 結果 parquet。
- `False`（production detail / eap detail）→ 不開 DuckDB file，每 chunk 直接 `merge_chunks_to_spool()`（pyarrow ParquetWriter 逐 batch append）。

**前端 spool 機制完全不變**：view 端點（`/summary` `/pareto` `/trend` `/detail`）仍是 in-memory DuckDB `read_parquet(spool_path)` → SQL → JSON，spool 格式不變確保逐 domain 安全回滾。

---

## 3. 遷移計畫（Migration Plan）

| 優先級 | 檔案 | 改動類型 | 預計工作量 | 備註 |
|---|---|---|---|---|
| **P0** | `core/base_chunked_duckdb_job.py`（新） | 新增基底抽象 class | L | 所有後續遷移的地基 |
| **P0** | `core/query_cost_policy.py`（新） | 新增 `classify_query_cost` + per-domain `CostPolicy` | M | 統一閾值，取代散落 env |
| **P0** | `core/oracle_arrow_reader.py`（新） | Oracle → pyarrow RecordBatch streaming（取代 `read_sql_df` 的 DataFrame 回傳） | M | 並行 chunk 各自一條連線 |
| **P1** | `workers/eap_alarm_worker.py` | 重構為繼承 `BaseChunkedDuckDBJob`（**POC**） | M | 已是零 pandas，驗證基底正確性 |
| **P1** | `services/job_registry.py` + `async_query_job_service.py` | 統一 enqueue 入口、加 `sync_fallback_allowed` / `always_async` flag | M | 消除 Pattern A/B 分裂 |
| **P2** | `services/production_history_*` | 改用基底；移除 RSS sync fallback 的 pandas 路徑 | M | 已是 parquet+DuckDB，改動最小 |
| **P2** | `services/reject_history_service.py` + `reject_dataset_cache.py` | groupby/pareto/trend 改 DuckDB SQL；view 端 `pd.read_parquet` → in-memory DuckDB | L | 移除 6 處 OOM 後檢查點 |
| **P2** | `services/resource_history_service.py` + `resource_dataset_cache.py` | `export_csv` 全量查詢改 chunk-to-spool；iterrows → DuckDB | L | 內部 base+OEE ThreadPool 已是正向參考 |
| **P3** | `services/material_trace_service.py` | `_execute_batched_query` 的 `pd.concat` → streaming-to-duckdb | M | 移除 concat 後才檢查的 guard |
| **P3** | `services/downtime_analysis_service.py` | `_bridge_jobid` Path B 改 DuckDB JOIN；保持「不可 row-chunk」分類（ADR-0003） | XL | 最高 OOM 風險也最難；需按 RESOURCEID 分組 |
| **P4** | `routes/query_tool_routes.py` | `@map_service_errors` timeout 同步等待 → 超閾值 enqueue RQ | M | 消除路徑 (C) 最後殘留 |
| **P4** | `routes/wip_routes.py` | 加 rowcount 預檢；超大查詢路由到 RQ | S | 即時 WIP 多為小查詢，影響面小 |
| **P5** | `services/batch_query_engine.py` | `merge_chunks`（pandas concat）標記 deprecated | M | 收尾，移除 pandas 熱路徑 |
| **P5** | 各 route 的 `*_ASYNC_DAY_THRESHOLD` env | 移除，改讀 `query_cost_policy` | S | 清理散落 env |

> 工作量：S = 半天、M = 1–2 天、L = 3–5 天、XL = > 1 週

---

## 4. 核心共用模組設計（Shared Infrastructure）

### 4.1 `BaseChunkedDuckDBJob` 抽象基底

```python
class BaseChunkedDuckDBJob(ABC):
    namespace: str                               # spool namespace, e.g. "eap_alarm"
    job_prefix: str                              # RQ meta prefix, e.g. "eap-alarm"
    requires_cross_chunk_reduction: bool = True  # False → 走 multi-parquet 輕量路徑
    chunk_strategy: ChunkStrategy                # TIME | ID_LIST | ROW_COUNT | SINGLE
    max_parallel: int = 3

    # ---- hooks（子類必須實作）----

    @abstractmethod
    def pre_query(self, params) -> QueryPlan:
        # 解析 filter、決定 chunk 邊界、算 deterministic query_id（spool 復用）
        ...

    @abstractmethod
    def build_chunk_sql(self, plan, chunk) -> tuple[str, dict]:
        # 產生單 chunk Oracle SQL（含 IN-list / ROW_NUMBER / date BETWEEN）
        ...

    def chunk_to_duckdb(self, conn, chunk_arrow) -> None:
        # 預設：INSERT INTO raw SELECT * FROM chunk_arrow（持 writer_lock）
        # 子類可覆寫做 per-chunk 預聚合
        ...

    @abstractmethod
    def post_aggregate(self, conn) -> str:
        # 在 DuckDB 內做最終 GROUP BY/JOIN，COPY TO spool.parquet，回傳 spool_path
        ...

    def progress_report(self, done, total, stage) -> None:
        # 預設 coarse bracket: 5(pre) → 15(first chunk) → 90(last) → 100(post)
        # chunk 多時可按 done/total 線性插值 15→90
        ...

    # ---- 模板方法（基底實作，子類不碰）----

    def run(self, job_id, **params):
        self.job_id = job_id
        plan = self.pre_query(params)
        self.progress_report(0, 0, "pre_query")
        chunks = self._decompose(plan)
        with self._open_job_duckdb(job_id) as conn:
            self._fan_out_chunks(conn, plan, chunks)   # ThreadPoolExecutor + writer_lock
            spool_path = self.post_aggregate(conn)
        register_final(self.namespace, plan.query_id, spool_path)
        complete_job(self.job_prefix, job_id, query_id=plan.query_id)
        self._cleanup_job_duckdb(job_id)
```

### 4.2 Oracle Connection Pool 策略

- **每個並行 chunk 一條獨立 Oracle 連線**（`oracledb` session pool）
- Pool 參數：`min=2, max=HEAVY_QUERY_MAX_CONCURRENT × per_job_parallel + headroom`（建議 max=12–15）
- **兩級並行控制**：
  1. **跨 job**：`global_concurrency` Redis semaphore，限制同時 active 的 RQ heavy job 數（= 3），語意從「保護同步」轉為「限制 RQ 並行打 Oracle」
  2. **job 內 chunk**：ThreadPoolExecutor `max_workers = min(max_parallel=3, pool_free_slots)`
- 取連線 timeout（10s），取不到則退化排隊，`effective_parallelism` 動態降階
- 每 chunk `finally: conn.close()` 歸還 pool，不可在 ThreadPoolExecutor 外持有

---

## 5. 風險與邊界條件（Risks & Constraints）

### 5.1 DuckDB 單 writer 限制

DuckDB 不支援多執行緒並發寫同一 file。**解法**：ThreadPoolExecutor 並行的是 Oracle fetch（I/O bound），fetch 回 Arrow 後，`INSERT INTO duckdb` 由 **單一 `threading.Lock` 序列化**。Arrow 轉換與 INSERT 很快（DuckDB C++ 層），瓶頸在 Oracle fetch 已被並行化，寫入序列化不構成實際瓶頸。

`requires_cross_chunk_reduction=False` 的 domain 走多 parquet（每 chunk 一檔），完全規避共享 writer。

### 5.2 Oracle Connection Pool 耗盡

N 個並發 job × M chunk 並行 = N×M 連線。緩解：global semaphore 限 job 數（3）× per-job chunk 並行（3）= 最多 9 連線 + headroom；pool max 設 12–15。需與 DBA 確認 Oracle session 配額。

### 5.3 RQ Worker 數量規劃

建議 heavy job 用**獨立低並發 queue**（`heavy-query`，per-queue max 2），輕 async job 用既有 queue。global semaphore 是最終護欄，即使 worker 多也限 3 個同時跑 Oracle heavy。

### 5.4 前端輪詢體驗

- **進度顯示**：沿用 coarse bracket（5→15→90→100）+ `completed_stages`，chunk 多時按完成數線性插值 15→90
- **超時處理**：前端設 client-side 上限（5 分鐘），逾時顯示「查詢仍在進行，請縮小範圍」
- **降級透明化**：enqueue 失敗靜默降同步時，回應帶 `mode: "sync_fallback"` 讓前端知道不需輪詢

### 5.5 回滾計畫

- **Feature flag per domain**：`<DOMAIN>_USE_UNIFIED_JOB=off`，出問題即關 flag 退回舊 `execute_primary_query`
- **Parquet schema 不變**：基底落的 spool 與舊路徑 schema 一致，前端 view 不需改動
- **DuckDB job file 清理**：孤兒 `{job_id}.duckdb` 由 TTL 清掃；rollback runbook 列明 `rm {DUCKDB_JOB_DIR}/*`

---

## 6. 第一個實作目標（First Milestone）

### POC 選擇：`eap_alarm`

**選擇理由：**

1. **已是目標形態的 80%**：零 pandas、Oracle → parquet（DuckDB `COPY TO`）→ in-memory DuckDB SQL view，改造它等於「驗證基底 class 能包住已知正確的流程」
2. **嚴格 always-async, no sync fallback**：不必處理降級分支，基底的 `run()` 模板可純粹驗證 chunk→duckdb→spool 主幹
3. **目前無 chunking**：worker 現在 `read_sql_df_slow` 兩次（events + detail）序列查、Oracle IN>999 才拆 OR clause，正好示範加上 `decompose_by_time_range` + ThreadPoolExecutor 並行帶來的提升
4. **不涉 cross-row reduction**：alarm 是 row-level，可安全 time chunk，不踩 ADR-0003 雷區
5. **前端不需改**：view 端點（summary/pareto/trend/detail）已是 in-memory DuckDB，spool 格式不變

### 最小改動清單

| # | 動作 | 檔案 |
|---|---|---|
| 1 | 新增 `BaseChunkedDuckDBJob` 基底（先只實作 `requires_cross_chunk_reduction=False` 路徑 + 並行 fan-out + writer lock） | `core/base_chunked_duckdb_job.py`（新） |
| 2 | 新增 Oracle → pyarrow RecordBatch streaming reader（取代 `read_sql_df_slow` 的 DataFrame 回傳） | `core/oracle_arrow_reader.py`（新） |
| 3 | 把 `run_eap_alarm_query_job` 重構為 `EapAlarmJob(BaseChunkedDuckDBJob)`：`pre_query`（解析 date/machines、算 spool key）、`build_chunk_sql`（events + detail，按 time range chunk）、`post_aggregate`（DuckDB `COPY TO` 現有 spool 路徑） | `workers/eap_alarm_worker.py` |
| 4 | 加 `EapAlarmJob` 進 `job_registry`，標 `always_async=True` | `services/job_registry.py` |
| 5 | 加 feature flag `EAP_ALARM_USE_UNIFIED_JOB=off`（預設 off），route enqueue 時依 flag 選新/舊 worker_fn | `routes/eap_alarm_routes.py` |
| 6 | `eap_alarm_service.py` 不動（view 端已是 in-memory DuckDB，spool schema 不變） | — |
| 7 | 測試：① 新舊路徑 spool parquet 內容等價（schema + rowcount）；② chunk 並行下結果無重複/遺漏；③ progress bracket 正確；④ Oracle 連線歸還無洩漏 | `tests/test_eap_alarm_service.py` 擴充 |

### 驗收標準

相同 `(date_from, date_to, machines)` 輸入，新路徑產出的 spool parquet 與舊路徑查詢結果等價，且：
- 跨 90 天查詢的 wall-time 因 chunk 並行而**下降**
- 記憶體峰值**不隨資料量線性上升**（DuckDB on-disk spill 生效）

POC 通過後，依 §3 優先級推進：`production_history`（同樣 parquet+DuckDB，改動最小）→ `reject` → `resource` → `material_trace` → `downtime`（最難，最後）。

---

## 關鍵設計總結

統一架構的本質是把「pandas in-memory」從所有熱路徑移除，用 eap_alarm 已驗證的模式取代：

```
Oracle 並行 chunk → Arrow RecordBatch → DuckDB（單 writer，on-disk spill）
→ post_aggregate（DuckDB SQL）→ parquet spool → in-memory DuckDB view → JSON
```

路徑 (C) 的所有同步慢查詢保護（timeout 等待、RSS fallback、semaphore-guarded ThreadPool）改為「`classify_query_cost` 超閾值即 enqueue RQ」，semaphore 角色從「保護同步」轉為「限制 RQ 並行打 Oracle」。前端 spool/view 機制完全不變，確保逐 domain feature-flag 可安全回滾。
