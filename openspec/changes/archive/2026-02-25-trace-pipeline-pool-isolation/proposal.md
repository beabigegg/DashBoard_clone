## Why

MSD trace pipeline 大範圍查詢（TMTT, 5 個月）產生 114K CIDs，event_fetcher 使用
`read_sql_df`（pool 連線）發送 ~230 條批次查詢，佔滿 connection pool，導致背景任務
（equipment cache、SYS_DATE）查詢時間從 1s 暴增到 500s，最終 Redis timeout +
gunicorn worker SIGKILL（2026-02-25 13:18 事件）。

## What Changes

- event_fetcher 和 lineage_engine 改用 `read_sql_df_slow`（獨立連線），不佔用 pool
- 降低 `EVENT_FETCHER_MAX_WORKERS` 預設 4→2、`TRACE_EVENTS_MAX_WORKERS` 預設 4→2，減少 Oracle 並行壓力
- 增加 `DB_SLOW_MAX_CONCURRENT` semaphore 容量 3→5，容納 event_fetcher 批次查詢
- event_fetcher 在 CID 數量 >10K 時跳過 L1/L2 cache（避免數百 MB JSON 序列化導致 Redis timeout 和 heap 膨脹）
- trace_routes events endpoint 早期釋放 `raw_domain_results` 並在大查詢後觸發 `gc.collect()`

## Capabilities

### New Capabilities

（無新增 capability）

### Modified Capabilities

- `event-fetcher-unified`: 改用非 pool 連線 + 降低預設並行數 + 大 CID 集跳過快取
- `lineage-engine-core`: 改用非 pool 連線（不佔用 pool，避免與 event_fetcher 競爭）
- `trace-staged-api`: 降低 domain 並行數 + 早期記憶體釋放 + 大查詢跳過 route-level cache
- `runtime-resilience-recovery`: slow query semaphore 容量增加以容納 trace pipeline 批次查詢

## Impact

- **後端 services**: event_fetcher.py, lineage_engine.py (import 切換)
- **routes**: trace_routes.py (並行數 + 記憶體管理)
- **config**: settings.py (DB_SLOW_MAX_CONCURRENT)
- **即時監控頁**: 不受影響（繼續用 pool）
- **前端**: 無修改
