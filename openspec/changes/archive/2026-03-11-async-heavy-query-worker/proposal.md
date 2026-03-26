## Why

Gunicorn 運行 2 workers x 4 threads = 8 HTTP threads。長區間查詢（reject-history、yield-alert、mid-section-defect）佔用 thread 1-5 分鐘，2-3 個並發即耗盡所有 thread，導致系統假死（health check 也無法回應）。現有 OOM 防護（memory guard、batch engine、spool）已到位，但 **thread 佔用問題未解決** — 即使不 OOM，長查詢仍佔住 Gunicorn thread。Trace 已用 RQ 背景 worker 解決此問題，需推廣到其他重查詢端點。

## What Changes

- **Async job queue for heavy queries**: 長區間查詢改為 HTTP 202 + RQ 背景 worker 執行 + 前端輪詢 job 狀態，Gunicorn thread 立即釋放
- **Dedicated RQ worker process**: 新增獨立 reject-query RQ worker（與 trace worker 分離），避免互相阻塞
- **Phase 0 即時防護**: 同步入口加全域並發快速拒絕（cache check → 並發檢查 → 503），縮短 inflight wait（180s→90s）
- **系統記憶體監控**: worker_memory_guard 增加系統層級記憶體檢查（psutil.virtual_memory），health endpoint 回報系統記憶體狀態
- **Gunicorn workers 增加**: 2→3 workers 提升一般操作容量
- **共用 async job 工具模組**: 從 trace_job_service.py 抽取通用 enqueue/status/progress 邏輯
- **前端 async polling**: 從 useTraceProgress.js 抽取共用輪詢 composable，reject-history 前端增加 async 分支與進度顯示

## Capabilities

### New Capabilities
- `async-query-job-service`: 通用 async job queue 服務（enqueue/status/progress），供 reject-history、yield-alert、MSD 共用
- `system-memory-monitoring`: 系統層級記憶體監控（total/available/pressure），整合到 health endpoint、worker_memory_guard、metrics_history

### Modified Capabilities
- `reject-query-backpressure`: POST /api/reject-history/query 增加 async 202 路徑；新增 GET /api/reject-history/job/<id> 端點；Phase 0 快速拒絕加入 cache check 前置
- `slow-query-concurrency-control`: inflight wait 預設從 180s 縮短為 90s；新增全域 Redis-based 並發限制器（跨 process）
- `worker-memory-tracking`: 增加系統記憶體（system_mem_available_mb、system_mem_used_pct）到 metrics snapshot；worker_memory_guard 增加系統記憶體門檻檢查
- `trace-staged-api`: 重構 trace_job_service.py 委託共用 async_query_job_service 模組（純重構，無行為變更）

## Impact

- **Backend**: 新增 3 個 Python 模組（async_query_job_service、reject_query_job_service、global_concurrency）；修改 reject_dataset_cache.py 抽取可重用查詢邏輯；修改 reject_history_routes.py 加入 202 路徑和 job status 端點；修改 worker_memory_guard.py、health_routes.py、metrics_history.py 加入系統記憶體監控
- **Frontend**: 新增 useAsyncJobPolling.js composable；修改 reject-history App.vue 增加 async 分支與進度 UI
- **Infrastructure**: 新增 rq-worker-reject process（scripts/start_server.sh）；GUNICORN_WORKERS 2→3；總計增加 ~700MB 記憶體
- **API**: 新增 `GET /api/reject-history/job/<id>`；POST /api/reject-history/query 可回 202（向下相容，短查詢仍回 200）
- **Configuration**: 新增 ~10 個環境變數（REJECT_ASYNC_ENABLED、SYSTEM_MEM_WARN_PCT 等），皆有合理預設值
