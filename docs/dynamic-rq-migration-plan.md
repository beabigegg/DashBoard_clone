# 動態 RQ 架構轉換計畫

> 建立日期：2026-06-13  
> 目標：將慢查詢接入 RQ 非同步框架，讓使用者看到明確進度；建立 Job Registry 讓未來新查詢類型免重複 boilerplate

---

## 背景與現況

### 現有 RQ 基礎設施

已有 9 種 RQ 非同步查詢（reject / yield-alert / production-history / trace / MSD / material），全部共用：
- `services/async_query_job_service.py` — 統一的 enqueue / status / progress / complete API
- Redis metadata schema：`{prefix}:job:{job_id}:meta`（HSET fields：status / progress / pct / stage / query_id / error / owner）
- 前端 `shared-composables/useAsyncJobPolling.ts` — 3s 輪詢，支援 onProgress callback

### 問題

| 問題 | 現狀 |
|---|---|
| 每種查詢類型需要 5 個新檔案 | job service、worker fn、route endpoint、prefix 常數、env var |
| 只有 reject-history 顯示進度條 | yield-alert / production-history 雖有 jobProgress state 但沒渲染 |
| 慢查詢（downtime / hold-history）仍同步 | 使用者等待 5-15 秒沒有任何回饋 |
| 無 job registry | 無法枚舉已知 job 類型，RQ monitor 依賴手動 env var |

---

## 執行階段

---

### 階段一：共用進度 UI 元件（純前端，零後端風險）

**估時：1–2 天**

#### 工作項目

**1-A. 建立 `AsyncQueryProgress.vue`**

路徑：`frontend/src/shared-ui/components/AsyncQueryProgress.vue`

Props：
```typescript
interface Props {
  active: boolean
  progress: string      // 後端 progress 欄位（如 "querying Oracle"）
  pct: number           // 0–100
  elapsedSeconds: number
  canCancel?: boolean   // 預設 true
  status?: string | null
}
// emits: ['cancel']
```

渲染：藍色 inline bar（不是 modal）、LoadingSpinner sm、進度文字、百分比、已等待秒數、取消按鈕。  
參考：`reject-history/App.vue:1478-1486` 的 `.async-job-status-bar`（直接提取即可）。  
CSS 以 `.async-job-progress` 為 base class，不依賴 `theme-*` scope（避免 teleport 問題）。

**1-B. 型別標準化**

路徑：`frontend/src/shared-composables/useAsyncJobPolling.ts`

補齊 `JobStatusResponse` interface（目前漏掉 pct / stage 宣告，消費者用 unknown cast）：
```typescript
export interface JobStatusResponse {
  status: string
  error?: string
  elapsed_seconds?: number
  progress?: string
  pct?: number          // ← 補上
  stage?: string        // ← 補上
  completed_stages?: string
  query_id?: string
  dataset_id?: string
  [key: string]: unknown
}
```

**1-C. 套用 AsyncQueryProgress 到 yield-alert / production-history**

- `yield-alert-center/App.vue`：jobProgress state 已有（lines 61-68），在 template 加 `<AsyncQueryProgress>` binding，補 cancel 邏輯
- `production-history/App.vue`：`useProductionHistory.ts` 已收集 jobProgress，expose `cancelJob()`，App.vue template 加元件

**1-D. 後端補齊 pct 更新**

路徑：`services/production_history_job_service.py`、`services/yield_alert_job_service.py`

在現有 `update_job_progress()` 呼叫補上 pct：
- initializing → `pct=0`
- querying Oracle → `pct=30`
- 完成 → `pct=100`（complete_job 前）

#### ✅ 階段一 Milestone 驗收

- [ ] `npm run test`（Vitest）：`AsyncQueryProgress.test.ts` 全通過
  - renders when active=true
  - hidden when active=false
  - shows pct bar when pct > 0
  - emits cancel event
- [ ] `npm run type-check`：無 TS 錯誤
- [ ] `npm run css:check`：無 CSS scope 違規
- [ ] 手動驗證（`npm run dev`）：
  - yield-alert 查詢時可見進度 bar
  - production-history 查詢時可見進度 bar
  - 取消按鈕可中止輪詢並恢復 UI 初始狀態
  - reject-history 原有進度 bar 無 regression

---

### 階段二：Job Registry 中央化

**估時：1 天**

#### 工作項目

**2-A. 建立 `job_registry.py`**

路徑：`src/mes_dashboard/services/job_registry.py`

```python
from dataclasses import dataclass
from typing import Callable, Dict, Any, Optional

@dataclass
class JobTypeConfig:
    job_type: str           # 全域唯一識別符，同時作為 Redis prefix
    queue_name: str         # RQ queue 名稱
    worker_fn: Callable     # execute_xxx_job function reference
    timeout_seconds: int = 1800
    ttl_seconds: int = 3600
    should_enqueue: Optional[Callable[[Dict[str, Any]], bool]] = None

_REGISTRY: Dict[str, JobTypeConfig] = {}

def register_job_type(config: JobTypeConfig) -> None:
    _REGISTRY[config.job_type] = config

def get_job_type_config(job_type: str) -> Optional[JobTypeConfig]:
    return _REGISTRY.get(job_type)

def list_registered_job_types() -> list[str]:
    return list(_REGISTRY.keys())
```

**2-B. 加入 `enqueue_job_dynamic()` 到 async_query_job_service**

路徑：`src/mes_dashboard/services/async_query_job_service.py`

```python
def enqueue_job_dynamic(
    job_type: str,
    owner: str,
    params: Dict[str, Any],
    job_id: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    config = get_job_type_config(job_type)
    if config is None:
        return None, f"Unknown job type: {job_type!r}"
    if config.should_enqueue and not config.should_enqueue(params):
        return None, "enqueue precondition not met"
    _job_id = job_id or f"{job_type}-{uuid.uuid4().hex[:12]}"
    return enqueue_job(
        queue_name=config.queue_name,
        worker_fn=config.worker_fn,
        owner=owner,
        job_id=_job_id,
        kwargs={"job_id": _job_id, **params},
        prefix=job_type,
        job_timeout=config.timeout_seconds,
        result_ttl=config.ttl_seconds,
    )
```

**2-C. 現有 9 種 job 加上宣告式 register**

在各 job service 末端加一行 `register_job_type(...)` 做登錄宣告。  
**不改動現有路由 dispatch 邏輯**（向後相容，保留舊 `enqueue_xxx()` 函數）：

| Service 檔案 | job_type | queue_name |
|---|---|---|
| `reject_query_job_service.py` | "reject" | "reject-query" |
| `yield_alert_job_service.py` | "yield_alert" | "yield-alert-query" |
| `production_history_job_service.py` | "production_history" | "production-history-query" |
| `trace_lineage_job_service.py` | "trace-lineage" | "trace-events" |
| `msd_seed_job_service.py` | "msd-seed" | "msd-analysis" |
| `msd_lineage_job_service.py` | "msd-lineage" | "msd-analysis" |
| `material_consumption_service.py` | "material-consumption" | "material-consumption-detail" |
| `material_trace_service.py` | "material-trace" | "trace-events" |

#### ✅ 階段二 Milestone 驗收

- [ ] `pytest tests/unit/services/test_job_registry.py`：全通過
  - `test_register_and_retrieve_job_type_config`
  - `test_unknown_job_type_returns_none`
  - `test_enqueue_job_dynamic_dispatches_to_correct_queue`
  - `test_enqueue_job_dynamic_respects_should_enqueue_gate`
  - `test_list_registered_job_types_returns_all_registered`
- [ ] `pytest tests/unit/services/test_async_query_job_service.py`：全通過（無 regression）
- [ ] `cdd-kit validate`：通過

---

### 階段三-A：Downtime Analysis 遷移至 RQ

**估時：2–3 天**

**現狀：** `POST /api/downtime-analysis/query` → `query_downtime_dataset_raw()` → Oracle 5–15 秒同步  
**目標：** 回傳 202 + job_id → 前端輪詢 + 進度條 → browser-DuckDB 載入 spool（ADR-0007 已就緒）

#### 工作項目

**3A-1. 新增 `downtime_query_job_service.py`**

路徑：`src/mes_dashboard/services/downtime_query_job_service.py`

```python
_JOB_TYPE = "downtime"
DOWNTIME_ASYNC_ENABLED = os.getenv("DOWNTIME_ASYNC_ENABLED", "true").lower() == "true"
DOWNTIME_ASYNC_DAY_THRESHOLD = int(os.getenv("DOWNTIME_ASYNC_DAY_THRESHOLD", "30"))

def should_use_async(params: dict) -> bool:
    if not DOWNTIME_ASYNC_ENABLED:
        return False
    days = (parse_date(params["end_date"]) - parse_date(params["start_date"])).days
    return days >= DOWNTIME_ASYNC_DAY_THRESHOLD and is_async_available()

def enqueue_downtime_query(params: dict, owner: str) -> Tuple[Optional[str], Optional[str]]:
    return enqueue_job_dynamic("downtime", owner=owner, params=params)

def execute_downtime_query_job(job_id: str, **params) -> None:
    update_job_progress("downtime", job_id, status="started", progress="初始化", pct=5)
    try:
        query_id = make_downtime_query_id(params)
        if _has_cached_spool(query_id):
            complete_job("downtime", job_id, query_id=query_id)
            return
        update_job_progress("downtime", job_id, status="running", progress="querying Oracle", pct=15)
        # 呼叫現有 query_downtime_dataset_raw() 寫入兩個 parquet spool
        store_downtime_base_events(...)       # pct=60 後更新
        store_downtime_job_bridge(...)        # pct=90 後更新
        complete_job("downtime", job_id, query_id=query_id)
    except Exception as exc:
        complete_job("downtime", job_id, error=str(exc))
        raise

register_job_type(JobTypeConfig(
    job_type="downtime",
    queue_name=os.getenv("DOWNTIME_WORKER_QUEUE", "downtime-query"),
    worker_fn=execute_downtime_query_job,
    timeout_seconds=int(os.getenv("DOWNTIME_JOB_TIMEOUT_SECONDS", "1800")),
    should_enqueue=should_use_async,
))
```

**3A-2. 修改 `downtime_analysis_routes.py`**

在 `POST /api/downtime-analysis/query` handler 加入 async 分流：
```python
if should_use_async(params):
    job_id, err = enqueue_downtime_query(params, owner=get_owner_token())
    if err:
        return error_response(err, 503)
    return success_response(
        {"async": True, "job_id": job_id, "status_url": f"/api/job/{job_id}?prefix=downtime"},
        status_code=202,
    )
# 短查詢走原同步路徑
```

新增 job status 端點（或複用通用 `/api/job/<id>?prefix=downtime`）。

**3A-3. 前端 downtime-analysis 加入進度 UI**

路徑：`frontend/src/downtime-analysis/`

- 加入 jobProgress state + `<AsyncQueryProgress>` 元件
- 接收 202 回傳的 `base_spool_url` + `jobs_spool_url`（browser-DuckDB 已有）
- 加 AbortController 支援取消

**3A-4. 新增 env-contract 條目**

路徑：`contracts/env/env-contract.md`

```
DOWNTIME_ASYNC_ENABLED      bool  true     是否啟用 downtime 非同步查詢
DOWNTIME_ASYNC_DAY_THRESHOLD int  30       超過此天數才走 RQ
DOWNTIME_WORKER_QUEUE       str   downtime-query  RQ queue 名稱
DOWNTIME_JOB_TIMEOUT_SECONDS int  1800     worker job timeout
```

#### ✅ 階段三-A Milestone 驗收

**後端單元測試：**
- [ ] `pytest tests/unit/services/test_downtime_query_job_service.py`：全通過
  - `test_should_use_async_true_when_days_exceed_threshold`
  - `test_should_use_async_false_when_disabled`
  - `test_enqueue_downtime_query_returns_job_id`
  - `test_execute_job_cache_hit_skips_oracle`
  - `test_execute_job_cache_miss_calls_oracle_writes_spool_completes`
  - `test_execute_job_exception_calls_complete_with_error_and_reraises`
  - `test_pct_milestones_called_in_order`（assert pct=5 → 15 → 60 → 90）

**資料準確性 Parity 測試（最重要）：**
- [ ] `pytest tests/unit/services/test_downtime_rq_parity.py`：全通過
  - 用固定 fixture（184k row 樣本）分別跑同步路徑和 RQ worker fn
  - assert base_events DataFrame：row count 相同、所有欄位值相同（DataFrame.equals()）
  - assert job_bridge DataFrame：同上
  - 覆蓋含跨班次事件的邊界 case（ADR-0003 seam-safety）

**整合測試：**
- [ ] `pytest tests/integration/test_downtime_async_routes.py`：全通過
  - `test_long_query_returns_202_with_job_id_and_status_url`
  - `test_short_query_returns_200_synchronously`（< threshold 仍走同步）
  - `test_status_endpoint_returns_progress`
  - `test_completed_job_returns_query_id`
  - `test_failed_job_returns_error`

**E2E 測試：**
- [ ] `tests/e2e/test_downtime_async_progress.py`（或 `.spec.ts`）：
  - 查詢（長範圍）→ 進度 bar 出現 → 消失 → 資料表有資料
  - 查詢後立即點取消 → UI 回到初始狀態

**env-contract：**
- [ ] `cdd-kit validate`：env-contract 通過

---

### 階段三-B：Hold History 遷移至 RQ

**估時：1–2 天**

**現狀：** `POST /api/hold-history/query` → `execute_primary_query()` → BatchQueryEngine → 1.9–10 秒同步  
**目標：** 同階段三-A

#### 工作項目

**3B-1. 新增 `hold_query_job_service.py`**

路徑：`src/mes_dashboard/services/hold_query_job_service.py`

與 downtime 相同結構。worker fn 包裝現有 `execute_primary_query()`，在每個 chunk 完成後更新 pct。

**3B-2. 修改 `hold_history_routes.py`**

加入 async 分流（同 3A-2 模式）。

**3B-3. 前端 hold-history 加入進度 UI**

**3B-4. env-contract 條目**

```
HOLD_ASYNC_ENABLED          bool  true
HOLD_ASYNC_DAY_THRESHOLD    int   90
HOLD_WORKER_QUEUE           str   hold-history-query
HOLD_JOB_TIMEOUT_SECONDS    int   1800
```

#### ✅ 階段三-B Milestone 驗收

- [ ] `pytest tests/unit/services/test_hold_query_job_service.py`：全通過（同 3A 結構）
- [ ] `pytest tests/unit/services/test_hold_rq_parity.py`：全通過
  - 含 open-hold escape（`RELEASETXNDATE IS NULL`）的 fixture
  - 含 row-count chunking 路徑
- [ ] `pytest tests/integration/test_hold_history_async_routes.py`：全通過
- [ ] E2E：查詢（長範圍）→ 進度 → 資料正確
- [ ] `cdd-kit validate`：通過

---

## 最終整體驗收

執行全套測試，確保無 regression：

```bash
# 後端
pytest tests/unit/services/test_job_registry.py
pytest tests/unit/services/test_async_query_job_service.py
pytest tests/unit/services/test_downtime_query_job_service.py
pytest tests/unit/services/test_downtime_rq_parity.py
pytest tests/unit/services/test_hold_query_job_service.py
pytest tests/unit/services/test_hold_rq_parity.py
pytest tests/integration/test_downtime_async_routes.py
pytest tests/integration/test_hold_history_async_routes.py
# 原有 RQ 測試無 regression
pytest tests/unit/services/test_reject_query_job_service.py
pytest tests/unit/services/test_production_history_job_service.py

# 前端
cd frontend && npm run test
cd frontend && npm run type-check
cd frontend && npm run css:check

# CDD
cdd-kit validate
```

**驗收標準：**

| 項目 | 標準 |
|---|---|
| 進度 UI | yield-alert / production-history / downtime / hold-history 查詢時均顯示進度 bar |
| Parity | downtime + hold-history RQ 路徑與同步路徑產生完全相同資料 |
| Regression | 所有原有 RQ 查詢（reject / yield / prod-history / trace / MSD）測試全通過 |
| Registry | 新增 job type 只需 `register_job_type()` + worker fn，不需新建 route file |
| E2E | downtime + hold-history：進度 bar 可見 → 資料正確呈現 → 取消可用 |

---

## 關鍵檔案索引

### 新增
| 路徑 | 說明 |
|---|---|
| `frontend/src/shared-ui/components/AsyncQueryProgress.vue` | 共用進度 UI 元件 |
| `frontend/src/shared-ui/components/__tests__/AsyncQueryProgress.test.ts` | 元件單元測試 |
| `src/mes_dashboard/services/job_registry.py` | Job type 中央 registry |
| `src/mes_dashboard/services/downtime_query_job_service.py` | Downtime RQ job service |
| `src/mes_dashboard/services/hold_query_job_service.py` | Hold History RQ job service |
| `tests/unit/services/test_job_registry.py` | Registry 單元測試 |
| `tests/unit/services/test_downtime_query_job_service.py` | Downtime job 單元測試 |
| `tests/unit/services/test_downtime_rq_parity.py` | Downtime parity 驗證 |
| `tests/unit/services/test_hold_query_job_service.py` | Hold job 單元測試 |
| `tests/unit/services/test_hold_rq_parity.py` | Hold parity 驗證 |
| `tests/integration/test_downtime_async_routes.py` | Downtime 整合測試 |
| `tests/integration/test_hold_history_async_routes.py` | Hold 整合測試 |

### 修改
| 路徑 | 修改內容 |
|---|---|
| `frontend/src/shared-composables/useAsyncJobPolling.ts` | 補齊 pct / stage 型別宣告 |
| `frontend/src/yield-alert-center/App.vue` | 加入 AsyncQueryProgress |
| `frontend/src/production-history/App.vue` | 加入 AsyncQueryProgress |
| `frontend/src/downtime-analysis/App.vue` | 加入 async job polling + AsyncQueryProgress |
| `frontend/src/hold-history/App.vue` | 加入 async job polling + AsyncQueryProgress |
| `src/mes_dashboard/services/async_query_job_service.py` | 加入 enqueue_job_dynamic() |
| `src/mes_dashboard/services/production_history_job_service.py` | 補 pct；加 register |
| `src/mes_dashboard/services/yield_alert_job_service.py` | 補 pct；加 register |
| `src/mes_dashboard/routes/downtime_analysis_routes.py` | 加 async 分流 + 202 回傳 |
| `src/mes_dashboard/routes/hold_history_routes.py` | 加 async 分流 + 202 回傳 |
| `contracts/env/env-contract.md` | 加 downtime + hold async 相關 env var |

### 參考（唯讀）
| 路徑 | 用途 |
|---|---|
| `services/reject_query_job_service.py` | 完整 RQ 週期的 canonical 範例 |
| `services/production_history_job_service.py` | enqueue 委派模式範例 |
| `tests/unit/services/test_reject_query_job_service.py` | 測試結構範例 |
| `tests/test_async_query_job_service.py` | core service 測試範例 |
| `reject-history/App.vue:1478-1486` | 進度 bar HTML 範例 |
| `docs/adr/0003-downtime-rowcount-chunking-exclusion.md` | Downtime chunking 約束 |
| `docs/adr/0007-downtime-browser-duckdb-compute-relocation.md` | Downtime spool 架構 |
