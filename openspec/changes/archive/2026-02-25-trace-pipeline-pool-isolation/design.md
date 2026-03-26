## Context

MSD trace pipeline 有三個階段：seed-resolve → lineage → events。
seed-resolve 已使用 `read_sql_df_slow`（獨立連線），但 lineage 和 events 仍用
`read_sql_df`（pool 連線，55s timeout）。大範圍查詢（114K CIDs）的 events 階段會
產生 ~230 條 Oracle 查詢，佔滿 pool（10+15=25 connections），導致背景任務和其他
worker 拿不到連線，最終 cascade failure（Redis timeout → worker SIGKILL）。

Connection pool 設計用於即時監控頁的短暫查詢（<1s），不適合 trace pipeline
的長時間批次作業。

## Goals / Non-Goals

**Goals:**
- trace pipeline（lineage + events）的 Oracle 查詢不佔用共用 pool
- 降低同時 Oracle 查詢數，減少 DB 壓力
- 大查詢（>10K CIDs）不觸發 Redis/L1 cache 寫入，避免 OOM 和 Redis timeout
- 背景任務（equipment cache、SYS_DATE）在 trace 執行期間可正常取得 pool 連線

**Non-Goals:**
- 加入 CID 數量上限（會導致資料不完整）
- 重構 event_fetcher 為 streaming/chunk 架構（未來改善）
- 修改前端 timeout 或即時監控頁

## Decisions

### D1: event_fetcher + lineage_engine 改用 `read_sql_df_slow`

**選擇**: import alias 切換 (`read_sql_df_slow as read_sql_df`)

**理由**: 最小改動量。所有 call site 不需修改，只改 import 行。`read_sql_df_slow`
建立獨立 oracledb 連線，不佔用 pool。

**替代方案考慮**:
- 建立第二個專用 pool → 過度工程，管理複雜
- 給 event_fetcher 自己的 semaphore → 增加兩套 semaphore 的管理複雜度

### D2: 降低 workers 預設值

**選擇**:
- `EVENT_FETCHER_MAX_WORKERS`: 4 → 2
- `TRACE_EVENTS_MAX_WORKERS`: 4 → 2

**理由**: Peak concurrent = 2 domains × 2 workers = 4 slow queries。
搭配 semaphore=5 留 1 slot 給其他 slow 查詢。仍可透過 env var 調整。

### D3: event_fetcher 批次查詢 timeout = 60s

**選擇**: 在 `_fetch_batch` 傳入 `timeout_seconds=60`

**理由**: 每個 batch query 正常 2-6s，300s 預設過長。60s 是 10x headroom。
lineage 不設限（CONNECT BY 可能較慢，保留 300s 預設）。

### D4: 大 CID 集跳過快取（threshold = 10K）

**選擇**: `CACHE_SKIP_CID_THRESHOLD = 10000`（env var 可調）

**理由**:
- 114K CIDs 的 cache key 是 sorted CIDs 的 MD5，同組查詢再次命中機率極低
- JSON 序列化 1M+ records 可達數百 MB，Redis `socket_timeout=5s` 必定 timeout
- L1 MemoryTTLCache 會在 heap 留住 GB 級 dict 達 TTL(300s)

route-level events cache 同樣在 CID > 10K 時跳過。

### D5: 早期記憶體釋放 + gc.collect

**選擇**: trace_routes events endpoint 在 MSD aggregation 後 `del raw_domain_results`，
大查詢後 `gc.collect()`。

**理由**: `raw_domain_results` 和 `results` 是同份資料的兩種 representation，
aggregation 完成後 grouped-by-CID 版本不再需要。`gc.collect()` 確保
Python 的 generational GC 及時回收大量 dict。

## Risks / Trade-offs

| 風險 | 緩解 |
|------|------|
| lineage 70K lots → 70+ sequential slow queries (~140s) 可能逼近 360s timeout | 已有 Redis cache TTL=300s，重複查詢走快取。首次最壞情況 ~280s < 360s |
| semaphore=5 在多個大查詢同時執行時可能排隊 | 每條 batch query 2-6s，排隊等待 <10s（wait timeout=60s 足夠）|
| 跳過 cache 後重複大查詢需重新執行 | 大查詢本身罕見（需 5 月範圍 + 特定站點），不值得佔用 cache 空間 |
| `gc.collect()` 有微小 CPU 開銷 | 僅在 CID>10K 時觸發，且在 response 建構後執行 |
