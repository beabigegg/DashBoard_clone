## Context

目前系統有 3 個 RQ worker（trace-events、reject-query、msd-analysis）處理重查詢，但 Production History 和 Yield Alert 兩個頁面仍在 Gunicorn worker 內同步執行 `read_sql_df_slow`。這兩個頁面已被迫實作窮人版限流（503 快速拒絕），表示它們的查詢量級已超出同步模式的合理範圍。

現有基礎設施：
- **後端**: `async_query_job_service.py` 提供通用 `enqueue_job` / `get_job_status` / `complete_job`
- **前端**: `useAsyncJobPolling.js` 提供 `pollJobUntilComplete` composable
- **範本**: `reject_query_job_service.py` + `reject_history_routes.py` 的 202 路徑是完整可複製模板

## Goals / Non-Goals

**Goals:**
- 將 production-history 和 yield-alert 的主查詢從 Gunicorn 同步路徑移至 RQ worker 背景執行
- 釋放 slow pool semaphore 槽位，降低多用戶同時查詢時的 503 率
- 前端無感切換：spool hit 仍即時回應 200，spool miss 改為 202 + polling
- 每個 worker 可透過環境變數獨立啟停（`*_ASYNC_ENABLED`）

**Non-Goals:**
- 不改動 `async_query_job_service.py` 核心邏輯
- 不改動 `useAsyncJobPolling.js` composable
- 不重構 production_history_service / yield_alert_service 的查詢邏輯本身
- 不處理 query_tool_service（調用模式太多樣，待後續獨立提案）
- 不處理 resource_history / hold_history（已有 DuckDB spool fast-path，優先度較低）

## Decisions

### D1: 複製 reject-query 模式，不抽象通用 worker factory

**選擇**: 為每個頁面各寫一個獨立的 `*_job_service.py`，結構照抄 `reject_query_job_service.py`。

**替代方案**: 抽象一個通用的 `GenericQueryJobService` 基類。

**理由**: 每個頁面的 `execute_*_job` 進入點需要不同的參數組合和快取檢查邏輯。reject / trace / msd 三個現有 job service 都是獨立檔案，保持一致性比引入抽象更好。~80 行的重複遠比過早抽象安全。

### D2: 每個頁面獨立 queue + 獨立 worker process

**選擇**:
- production-history → queue `production-history-query`，獨立 worker process
- yield-alert → queue `yield-alert-query`，獨立 worker process

**替代方案**: 共用一個 `heavy-query` queue。

**理由**: 獨立 queue 確保一個頁面的慢查詢不會餓死另一個頁面。這與現有 reject/msd 的隔離策略一致。每個 worker 的 DB 連線池獨立（`DB_POOL_SIZE=2 DB_MAX_OVERFLOW=1`），記憶體佔用可控。

### D3: Route 層的 async 判斷策略

**Production History**: 所有主查詢一律走 async（BatchQueryEngine chunk 查詢本身就是重查詢），除非 spool 已有結果。

**Yield Alert**: 所有主查詢一律走 async（`execute_primary_query` 內含多個 `read_sql_df_slow`），除非 spool/cache 已有結果。

**理由**: 不像 reject-history 有「短日期範圍走同步」的判斷（`REJECT_ASYNC_DAY_THRESHOLD`），這兩個頁面的查詢無論日期範圍都是重查詢，簡化判斷邏輯。若 RQ worker 不可用（`is_async_available()` 返回 False），回退到原有同步路徑。

### D4: 移除窮人限流，保留 RQ 不可用時的同步回退

**選擇**:
- 移除 yield_alert_routes 的 `get_slow_query_active_count` 快速拒絕
- 移除 production_history_routes 的 `heavy_query_overloaded` 處理
- 但保留同步路徑作為 RQ 不可用時的 fallback

**理由**: Worker 機制本身就是併發控制——每個 queue 一個 worker，自然串行處理。窮人限流在 worker 模式下是多餘的。但 RQ 或 Redis 掛掉時需要 graceful degradation。

### D5: 前端 202 處理直接複製 reject-history 模式

**選擇**: 在 `useProductionHistory.js` 的 `runQuery` 和 `yield-alert-center/App.vue` 的查詢函數中加入 202 分支，呼叫 `pollJobUntilComplete`。

**理由**: `useAsyncJobPolling.js` 已設計為可複用，reject-history 的 `App.vue` 是完整範本。不需要進一步抽象。

## Risks / Trade-offs

**[Worker 進程數增加]** → 從 3 個 RQ worker 增加到 5 個，每個佔 `DB_POOL_SIZE=2 + DB_MAX_OVERFLOW=1` = 3 條 Oracle 連線。總新增 6 條連線。Mitigation: 透過 `*_WORKER_ENABLED` 環境變數可按需啟停；prod 環境 Oracle 連線池充裕。

**[記憶體佔用]** → 每個 worker process 約 200-400MB RSS（依查詢結果集大小）。新增 2 個 worker ≈ 額外 400-800MB。Mitigation: 現有 worker-self-healing 機制（watchdog）已覆蓋 RQ worker 的 RSS 監控。

**[RQ 不可用時的回退]** → 若 Redis 掛掉或 worker 未啟動，查詢回退到 Gunicorn 同步路徑。此時行為與改動前完全相同（包括原有的 slow pool 壓力問題）。這是刻意的 graceful degradation。

**[前端 UX 變化]** → 原本用戶看到的是一直轉圈等到底（或 timeout），改動後看到 202 + polling 進度提示。體感可能變慢（因為多了 polling 間隔），但實際上釋放了 Gunicorn worker 不阻塞其他請求。Mitigation: polling 間隔 3 秒（與 reject-history 一致），可接受。

## Open Questions

- 暫無。模式完全複製自 reject-query，無需新的架構決策。
