## Context

Gunicorn 以 2 workers × 4 threads = 8 HTTP threads 運行。長區間查詢（reject-history >10 天、yield-alert、mid-section-defect 冷快取）佔用 thread 1-5 分鐘，2-3 個並發即耗盡所有 thread，導致系統假死。

Trace 功能已使用 RQ (Redis Queue) 實現背景 worker 模式：`trace_job_service.py` 提供 enqueue/status/stream，`useTraceProgress.js` 提供前端輪詢。此模式已驗證可行，需推廣到其他重查詢端點。

現有防護（per-IP rate limit、per-process semaphore、memory guard）無法解決 thread 佔用問題——它們只控制「是否允許查詢」，不改變「查詢在哪個 process 執行」。

## Goals / Non-Goals

**Goals:**
- 長查詢不佔用 Gunicorn thread，改由 RQ worker 背景執行
- 前端透明感知 async/sync 路徑，短查詢仍同步回應
- 系統記憶體監控防止新增 process 導致 OOM
- 即時防護（Phase 0）可獨立部署，不依賴 RQ 改動

**Non-Goals:**
- 不改變查詢 SQL 或 Oracle 連線架構
- 不引入新的 message queue（繼續使用 RQ + Redis）
- 不拆分 Gunicorn 為多實例（不需要 nginx 路由）
- 不將背景服務（cache-updater 等）從 Gunicorn worker 移出

## Decisions

### D1: 重查詢走 RQ worker，不走 Gunicorn thread

**選擇**: 長區間查詢 enqueue 到 RQ，Gunicorn 立即回 202。
**替代方案**: (a) 增加 Gunicorn workers/threads — 治標不治本，記憶體壓力更大。(b) asyncio — 需要大規模重構，且 Oracle driver 不支援。
**理由**: RQ 已在 Trace 驗證可行，worker 獨立 process 有自己的記憶體空間，不影響 HTTP 服務。

### D2: 兩個獨立 RQ worker process（trace + reject）

**選擇**: 分離 trace-events 和 reject-query 為兩個 RQ worker process。
**替代方案**: (a) 共用單一 worker — trace job 可達 30 分鐘，會阻塞 reject job。(b) 共用但加優先級 — 仍然序列處理，reject 等待 trace 完成。
**理由**: 獨立 process 互不阻塞，reject 通常 1-5 分鐘，不應被 trace 延遲。記憶體成本 +400MB 可接受。

### D3: 共用 async job 工具模組，不用抽象類別

**選擇**: 建立 `async_query_job_service.py` 提供函式級工具（enqueue_job、get_job_status、update_job_progress），各 domain 有自己的 worker entry point。
**替代方案**: 建立 AbstractAsyncJob base class — 增加不必要的繼承複雜度。
**理由**: 函式組合比類別繼承更靈活，與現有 `trace_job_service.py` 風格一致。

### D4: Phase 0 快速拒絕在 cache check 之後

**選擇**: 503 拒絕前先查 cache（L1/L2/spool），確保重試可沿用已完成結果。
**替代方案**: 直接在 route 最前面檢查並發 — 會導致已完成查詢的重試也被拒絕。
**理由**: query_id 是確定性 hash（SHA256 from mode + dates + containers），相同參數 = 相同 query_id，cache hit 直接回 200 不觸發新查詢。

### D5: 前端簡單 loading + 進度文字，不做 toast 模式

**選擇**: 複用現有 loading overlay，加入進度文字（「背景查詢中... 7/10 區段完成」）和取消按鈕。
**替代方案**: Toast 通知 + 可繼續操作 — 需要跨頁面狀態管理，複雜度高。
**理由**: 最小改動，使用者體驗與現有同步查詢一致（只是等待時間有進度提示）。

### D6: 系統記憶體監控整合到現有 worker_memory_guard

**選擇**: 在現有 15 秒週期檢查中加入 `psutil.virtual_memory()` 系統記憶體檢查。
**替代方案**: 獨立 process 監控 — 增加部署複雜度。
**理由**: 複用現有基礎設施，不增加新 process。門檻：>85% 警告+eviction、>92% 拒絕新重查詢。

### D7: inflight wait 縮短為 90 秒

**選擇**: `REJECT_ENGINE_QUERY_WAIT_SECONDS` 預設 180→90。
**理由**: 無直接 benchmark 佐證 chunk 耗時，但 Oracle timeout 為 300s、chunk grain 為 10 天。90 秒為保守折衷——足夠等待多數正常 chunk，又不至於長時間佔 thread。Wait 只影響「等待相同 query_id 完成」的 thread，不影響執行中的查詢。

## Risks / Trade-offs

- **[RQ worker 記憶體]** 新增 2 個 RQ worker + 1 個 Gunicorn worker 共 +700MB → 啟動前檢查系統記憶體餘裕，不足時減少 worker 數量
- **[RQ worker 故障]** RQ worker crash 後 job 無回應 → `is_async_available()` 健康檢查（60s TTL cache），不可用時 graceful fallback 到同步路徑
- **[DB 連線共用]** RQ worker 需要獨立 Oracle 連線 → 使用現有 `get_engine()` 在 worker process 初始化，slow_pool 容量需檢查
- **[前端相容性]** 202 回應是新行為 → 前端必須同步更新，否則會誤判為錯誤；短查詢仍回 200 確保向下相容
- **[inflight wait 90s]** 若 chunk 實際耗時 >90s，等待方會收到 503 → 重試安全（cache check 在前），不會導致重複執行
