## Phase 1: RQ Worker 加強

- [x] 1.1 修改 `src/mes_dashboard/services/async_query_job_service.py`:
  - `enqueue_job()` 新增 `retry` 參數（預設 `Retry(max=2, interval=[30, 60])`）
  - `from rq import Retry` import
  - `queue.enqueue()` 傳入 `retry` 參數
  - 保留 `retry=None` 的 bypass 路徑（向後相容）
- [x] 1.2 修改 `src/mes_dashboard/services/async_query_job_service.py`:
  - `ASYNC_JOB_DEFAULT_TIMEOUT_SECONDS` 預設值從 `1800` 改為 `600`
- [x] 1.3 修改 `src/mes_dashboard/services/async_query_job_service.py`:
  - `complete_job()` 的 `error is not None` 路徑新增 `logger.warning("Job failed: prefix=%s job_id=%s error=%s", prefix, job_id, error)`
  - 新增 module-level counter `_FAILED_JOB_COUNT` (thread-safe)
  - 新增 `get_failed_job_count()` 供 metrics 收集
- [x] 1.4 測試 Phase 1:
  - 更新 `tests/test_reject_query_job_service.py` 驗證 retry 參數傳遞
  - 新增 `complete_job` 失敗路徑的 warning log 斷言
  - 驗證 timeout 預設值

## Phase 2: 慢端點處理

### 2A: msd/analysis 非同步化

- [x] 2.1 建立 `src/mes_dashboard/services/msd_query_job_service.py`:
  - `enqueue_msd_analysis(start_date, end_date, station, direction, loss_reasons)` — 呼叫 `enqueue_job(queue_name="msd-analysis", ...)`
  - `_execute_msd_analysis(**kwargs)` — worker 入口，呼叫 `query_analysis()`，結果存入 cache，呼叫 `complete_job()`
  - Queue 名稱從 `MSD_WORKER_QUEUE` 環境變數讀取（預設 `msd-analysis`）
  - Timeout 從 `MSD_JOB_TIMEOUT_SECONDS` 環境變數讀取（預設 `600`）
- [x] 2.2 修改 `src/mes_dashboard/routes/mid_section_defect_routes.py`:
  - `/analysis` endpoint: 先查 cache → hit 直接回 200；miss 檢查 `is_async_available()` → True 時 enqueue 回 202；False 時同步執行（fallback）
  - 新增 `GET /api/mid-section-defect/analysis/job/<job_id>` — 回傳 job status
  - 新增 `GET /api/mid-section-defect/analysis/job/<job_id>/result` — 回傳完成結果
- [x] 2.3 建立 `deploy/mes-dashboard-msd-worker.service`:
  - 複製 `mes-dashboard-reject-worker.service` 為模板
  - 修改 queue 為 `msd-analysis`，其餘設定一致（Restart=always, MemoryMax=4G）
- [x] 2.4 修改 `scripts/start_server.sh`:
  - 新增 msd worker 啟動/停止邏輯（與 trace/reject worker 同模式）
- [x] 2.5 修改前端 MSD analysis 頁面:
  - 偵測 202 回應 → 使用 `useAsyncJobPolling` 輪詢
  - 顯示 loading/progress 狀態
  - 完成後 fetch result 並渲染
- [x] 2.6 測試 2A:
  - `tests/test_msd_query_job_service.py` — enqueue、execute、failure 路徑
  - 更新 `tests/test_mid_section_defect_service.py` — 非同步 path 驗證

### 2B: Dataset 預熱

- [x] 2.7 修改 `src/mes_dashboard/services/reject_dataset_cache.py`:
  - 新增 `ensure_dataset_loaded()` 公開函式（檢查 Redis → miss 時執行 Oracle 查詢 → 存入 Redis）
- [x] 2.8 修改 `src/mes_dashboard/services/yield_alert_dataset_cache.py`:
  - 新增 `ensure_dataset_loaded()` 公開函式（同上模式）
- [x] 2.9 修改 `src/mes_dashboard/core/cache_updater.py`:
  - 新增 `_warmup_reject_dataset()` — 呼叫 `reject_dataset_cache.ensure_dataset_loaded()`
  - 新增 `_warmup_yield_alert_dataset()` — 呼叫 `yield_alert_dataset_cache.ensure_dataset_loaded()`
  - 新增 `_warmup_reject_options()` — 呼叫 `get_filter_options()` 預熱 route cache
  - 在 `_run()` loop 中加入三個 warmup 呼叫（每個用 try/except 包裹，失敗不阻塞）
  - 首次啟動時立即執行 warmup（不等 interval）
- [x] 2.10 測試 2B:
  - `tests/test_cache_updater.py` — 驗證 warmup 任務被呼叫
  - 驗證 warmup 失敗不阻塞 CacheUpdater 主迴圈

### 2C: reject-history 30d 聚合優化

- [x] 2.11 修改 `src/mes_dashboard/services/reject_dataset_cache.py`:
  - 對大 DataFrame 的 groupby 維度欄位（`TXN_DAY`, `LOSSREASONNAME` 等）轉為 `pd.Categorical` dtype
  - 在 `_store_df()` 或 dataset 建構完成後統一轉換
- [x] 2.12 測試 2C:
  - `tests/test_reject_dataset_cache.py` — 驗證聚合結果與轉換前一致（parity test）

## Phase 3: 快取架構微調

- [x] 3.1 修改 `src/mes_dashboard/services/hold_dataset_cache.py`:
  - `_dataset_cache = ProcessLevelCache(ttl_seconds=900, max_size=3)` （原 8）
- [x] 3.2 修改 `src/mes_dashboard/services/resource_dataset_cache.py`:
  - `_dataset_cache = ProcessLevelCache(ttl_seconds=900, max_size=3)` （原 8）
- [x] 3.3 修改 `src/mes_dashboard/services/reject_dataset_cache.py`:
  - `_dataset_cache` max_size 改為 3 （原 8）
- [x] 3.4 修改 `src/mes_dashboard/services/yield_alert_dataset_cache.py`:
  - `_dataset_cache` max_size 改為 2 （原 3）
- [x] 3.5 修改 `src/mes_dashboard/core/cache.py`:
  - `MemoryTTLCache.__init__()` 新增 `max_size=256` 參數
  - `set()` 方法：超過 max_size 時淘汰最舊（最早寫入）的 entry
  - 既有 `get()` 行為不變
- [x] 3.6 測試 Phase 3:
  - 更新 `tests/test_cache.py` — MemoryTTLCache max_size eviction 測試
  - 驗證各 dataset cache 建構時 max_size 正確

## Phase 4: 觀測性補齊

- [x] 4.1 修改 `src/mes_dashboard/core/cache.py`:
  - `MemoryTTLCache` 新增 `_hit_count` 和 `_miss_count` counter
  - `get()` 方法：hit 時 `_hit_count += 1`，miss 時 `_miss_count += 1`
  - 新增 `get_hit_miss_counts()` → `{"hits": int, "misses": int}`
  - 新增 `reset_hit_miss_counts()` → 讀取並歸零（delta 模式）
- [x] 4.2 修改 `src/mes_dashboard/core/metrics_history.py`:
  - `CREATE_TABLE_SQL` 及 `_MIGRATION_COLUMNS` 新增 `cache_hit_count INTEGER`, `cache_miss_count INTEGER`
  - collector 快照時呼叫 `reset_hit_miss_counts()` 取 delta 值寫入
- [x] 4.3 修改 `src/mes_dashboard/core/database.py`:
  - `read_sql_df()` 新增可選 `caller: str = "unknown"` 參數
  - `read_sql_df_slow()` 同上
  - 慢查詢 warning log 格式改為：`"Slow query (%s, %.2fs): %s..."` % (caller, elapsed, sql_preview)
  - 逐步在各 service 呼叫處加上 caller tag（不阻塞，可分批）
- [x] 4.4 修改 `src/mes_dashboard/core/metrics_history.py` 或 `routes/health_routes.py`:
  - 快照收集時檢查 `rq_queue_depth > 0 and rq_workers_total == 0` → emit WARNING log
- [x] 4.5 測試 Phase 4:
  - `tests/test_cache.py` — hit/miss counter 測試
  - `tests/test_metrics_history.py` — 新欄位 migration 測試
  - 驗證 caller tag 不影響既有 slow log 行為

## Phase 5: 收尾

- [x] 5.1 更新 `contract/api_inventory.md`:
  - 新增 `GET /api/mid-section-defect/analysis/job/<job_id>` 和 `/result` 端點
  - 更新 `mid_section_defect_routes.py` 描述（analysis 可能回 202）
- [x] 5.2 更新 `.env.example`:
  - 新增 `MSD_WORKER_QUEUE`, `MSD_JOB_TIMEOUT_SECONDS`, `MSD_JOB_TTL_SECONDS` 環境變數
- [x] 5.3 驗證全部測試通過:
  - `pytest tests/ -v` 全部綠燈
