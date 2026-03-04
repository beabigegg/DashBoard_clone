# OOM 防護跨工具改善 — Agent 工作架構

> 基於 `oom_cache_cross_apply_analysis.md` 痛點分析 + 4 個研究 agent 的代碼深度掃描結果

---

## Agent 架構總覽

```
                    ┌─────────────────────┐
                    │  agent-shared (P0)  │  ← 必須先完成
                    │  共用記憶體守衛抽離  │
                    └─────────┬───────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
  ┌───────────────┐ ┌───────────────┐ ┌───────────────┐
  │ agent-mt (P1) │ │ agent-qt (P1) │ │ agent-md (P1) │  ← 可平行
  │ Material Trace│ │ Query Tool    │ │ Mid-Defect    │
  └───────┬───────┘ └───────┬───────┘ └───────┬───────┘
          │                 │                 │
          └─────────────────┼─────────────────┘
                            ▼
                    ┌─────────────────────┐
                    │   agent-qa (P2)     │  ← 最後驗證
                    │   測試 + 壓力測試    │
                    └─────────────────────┘
```

---

## Agent 0: agent-shared — 共用記憶體守衛抽離

### 目標
將 `reject_dataset_cache.py` 的私有 `_enforce_interactive_memory_guard()` 抽離為 `core/` 層可重用元件。

### 發現
- `_enforce_interactive_memory_guard` 目前是 `reject_dataset_cache.py` 的 **module-private 函式**
- 依賴 `_df_memory_mb()` 和 `_process_rss_mb()` 兩個 helper（也是同檔案 private）
- `_process_rss_mb()` 與 `worker_memory_guard._current_rss_mb()` **完全重複**
- 4 個常數全部硬編碼為 reject-history 專用（`REJECT_DERIVE_*`）

### 任務清單

| # | 任務 | 改動檔案 | 行數估計 |
|---|------|---------|---------|
| S1 | 建立 `core/interactive_memory_guard.py` | 新建 | ~60 行 |
| S2 | 抽離 `df_memory_mb()` + `process_rss_mb()` 為 public | 新檔案 | 含在 S1 |
| S3 | 主函式 `enforce_dataset_memory_guard()` — 參數化閾值（帶預設值） | 新檔案 | 含在 S1 |
| S4 | `reject_dataset_cache.py` 改為 import 新元件 | 修改 | ~15 行 |
| S5 | 合併 `worker_memory_guard._current_rss_mb()` 重複邏輯 | 修改 | ~10 行 |
| S6 | 新增單元測試 | 新建 | ~80 行 |

### 新元件 API 設計（草案）

```python
# core/interactive_memory_guard.py

def df_memory_mb(df: pd.DataFrame) -> float: ...
def process_rss_mb() -> Optional[float]: ...

def enforce_dataset_memory_guard(
    df: pd.DataFrame,
    *,
    operation: str,
    query_id: str = "",
    max_input_mb: float = 96.0,
    max_projected_rss_mb: float = 1100.0,
    working_set_factor: float = 1.8,
) -> None:
    """跨工具通用 — DataFrame + RSS 投影守衛。超限 raise MemoryError。"""
```

---

## Agent 1: agent-mt — Material Trace

### 痛點（代碼驗證）

| 痛點 | 嚴重度 | 代碼位置 | 驗證結果 |
|------|:------:|---------|---------|
| 分頁重查 Oracle | 🔴 | `service.py:246` `forward_query()` | 每次翻頁走 `_execute_batched_query()` 完整重查 |
| Export 全量 materialize | 🔴 | `service.py:315` `export_csv()` | `read_sql_df_slow` + `to_csv().encode()` 全在記憶體 |
| 正向查詢無行數上限 | 🟡 | `forward_by_lot.sql` / `forward_by_workorder.sql` | 確認無 FETCH FIRST |
| 記憶體守衛不投影 RSS | 🟡 | `service.py:156` `_check_memory_guard()` | 只檢 DataFrame 大小，不看 RSS |
| 完全零快取 | 🔴 | service.py 全域 import | 無任何 Redis/LRU/DuckDB import |

### 任務清單

| # | 任務 | 改動檔案 | 行數估計 | 優先序 |
|---|------|---------|---------|:---:|
| MT1 | Redis 查詢結果快取 — key=(mode,values,wc_groups) hash, TTL=5min | `service.py` | ~80 行 | P0 |
| MT2 | 分頁/匯出讀快取 — `_paginate()` 從 Redis 讀取而非重查 | `service.py` | ~40 行 | P0 |
| MT3 | 升級記憶體守衛 — `_check_memory_guard` 改用 `enforce_dataset_memory_guard` | `service.py` | ~15 行 | P1 |
| MT4 | 正向 SQL 加 `FETCH FIRST 50001 ROWS ONLY` + truncation 標記 | `forward_by_*.sql` + `service.py` | ~25 行 | P1 |
| MT5 | Export 串流化 — 改用 `read_sql_df_slow_iter` + generator yield | `service.py` | ~40 行 | P2 |
| MT6 | 強制 GC — `_execute_batched_query` 後 `gc.collect()` | `service.py` | ~5 行 | P2 |
| MT7 | 新增/更新測試 | `tests/test_material_trace_*.py` | ~100 行 | — |

### 快取架構設計

```
POST /query (page=1)
  → hash = md5(mode + sorted(values) + sorted(wc_groups))
  → cache_key = "mt:result:{hash}"
  → cache MISS → Oracle 查詢 → DataFrame → store Redis (parquet bytes, TTL=5min)
  → _paginate(df, page=1, per_page=50)

POST /query (page=2)  ← 翻頁
  → same cache_key
  → cache HIT → Redis load DataFrame
  → _paginate(df, page=2, per_page=50)  ← 不打 Oracle

POST /export
  → same cache_key
  → cache HIT → Redis load DataFrame → streaming CSV
```

---

## Agent 2: agent-qt — Query Tool

### 痛點（代碼驗證）

| 痛點 | 嚴重度 | 代碼位置 | 驗證結果 |
|------|:------:|---------|---------|
| 明細全量回傳 | 🔴 | `lot_history.sql` 無 LIMIT | lot-history/associations/equipment-lots 全無 server-side 分頁 |
| EventFetcher 無累積上限 | 🔴 | `event_fetcher.py:251` `_fetch_and_group_batch` | `grouped` dict 無限累積，fetchmany 只節省 Oracle 端 |
| equipment-lots 無快取+全量 | 🔴 | `service.py:1604` | 365天×20台→10萬+行全量 DataFrame，零快取 |
| CSV export 全量 materialize | 🟡 | `routes.py:816` | 先 `get_lot_history_batch()` 全量，再 yield CSV |
| 無互動式 RSS 守衛 | 🟡 | 全部服務函數 | 完全依賴被動式 worker_memory_guard |
| 48M 無索引表 | 🟡 | `lot_split_merge_history.sql` | fast mode 有 6月+500行限制（部分緩解） |

### 任務清單

| # | 任務 | 改動檔案 | 行數估計 | 優先序 |
|---|------|---------|---------|:---:|
| QT1 | EventFetcher 加 total-result 守衛 — 累積 > N 行截斷+標記 | `event_fetcher.py` | ~25 行 | P0 |
| QT2 | 重型端點前加 RSS 投影守衛 | `service.py` (5 處) | ~30 行 | P0 |
| QT3 | lot-history SQL 加 OFFSET/FETCH 分頁 | `lot_history.sql` + `service.py` + `routes.py` | ~60 行 | P1 |
| QT4 | equipment-lots SQL 加 OFFSET/FETCH 分頁 | `equipment_lots.sql` + `service.py` + `routes.py` | ~60 行 | P1 |
| QT5 | equipment-lots 加 Redis 快取（同 equipment_status_hours 模式） | `service.py` | ~30 行 | P1 |
| QT6 | split_merge_history full mode 預設 fast | `service.py:1128` | ~10 行 | P2 |
| QT7 | 重型端點 response 後 gc.collect() | `routes.py` | ~10 行 | P2 |
| QT8 | 新增/更新測試 | `tests/test_query_tool_*.py` | ~150 行 | — |

### EventFetcher 守衛設計

```python
# event_fetcher.py — _fetch_and_group_batch 內
_TOTAL_RESULT_MAX_ROWS = int(os.getenv("EVENT_FETCHER_MAX_TOTAL_ROWS", "500000"))

total_row_count += 1
if total_row_count > _TOTAL_RESULT_MAX_ROWS:
    logger.warning("EventFetcher total rows %d exceeds limit %d, truncating",
                   total_row_count, _TOTAL_RESULT_MAX_ROWS)
    meta["truncated"] = True
    break  # 停止累積，回傳已有資料
```

---

## Agent 3: agent-md — Mid-Section Defect

### 痛點（代碼驗證）

| 痛點 | 嚴重度 | 代碼位置 | 驗證結果 |
|------|:------:|---------|---------|
| RQ 健康檢查只看 import | 🔴 | `trace_job_service.py:51` | `_check_rq_available()` 只做 `import rq`，不 ping Redis，不檢 worker |
| Sync fallback 無 RSS 守衛 | 🔴 | `trace_routes.py:662` | enqueue 失敗→直接走 sync，MSD 甚至不拒絕 >50K CIDs |
| Stampede lock 只在 legacy path | 🟡 | `service.py:169` | 三階段 events 端點完全無 stampede 防護 |
| Lock wait 90s fail-open | 🟡 | `service.py:195` | 等 90s 後直接執行，可能 stampede |
| Aggregation 全量在記憶體 | 🟡 | `service.py:292` | `build_trace_aggregation_from_events` 需完整 events dict |
| Export 全量 materialize | 🟡 | `service.py:644` | `query_analysis()` 全量 → yield CSV |

### 任務清單

| # | 任務 | 改動檔案 | 行數估計 | 優先序 |
|---|------|---------|---------|:---:|
| MD1 | RQ 健康監控升級 — 加 `conn.ping()` + worker 存活檢查 + TTL cache | `trace_job_service.py` | ~40 行 | P0 |
| MD2 | Sync 路徑 RSS 投影守衛 — events 入口處檢查，超限返回 503 | `trace_routes.py` | ~35 行 | P0 |
| MD3 | RQ 不可用時前端降級提示 — 健康端點 + 前端提示 | `health_routes.py` + Vue | ~30 行 | P1 |
| MD4 | Stampede lock timeout 延長 — 90s → 180s | `service.py` 常數 | ~5 行 | P1 |
| MD5 | Events 端點加 stampede lock | `trace_routes.py` | ~20 行 | P1 |
| MD6 | Aggregation 前 RSS checkpoint | `service.py:292` | ~15 行 | P2 |
| MD7 | 新增/更新測試 | `tests/test_mid_section_defect_*.py` | ~120 行 | — |

### RQ 健康檢查升級設計

```python
# trace_job_service.py

_RQ_HEALTH_TTL = 60  # 秒
_rq_health_cache = {"available": None, "checked_at": 0}

def is_async_available() -> bool:
    now = time.monotonic()
    if now - _rq_health_cache["checked_at"] < _RQ_HEALTH_TTL:
        return _rq_health_cache["available"]

    if not _check_rq_available():
        _update_cache(False, now)
        return False

    conn = get_redis_client()
    if conn is None:
        _update_cache(False, now)
        return False

    try:
        conn.ping()  # ← 新增：實際 ping Redis
    except Exception:
        _update_cache(False, now)
        return False

    # 新增：檢查 worker 存活
    try:
        from rq import Queue
        q = Queue("trace", connection=conn)
        if q.count > 100:  # queue 堵塞
            logger.warning("RQ queue backed up: %d jobs", q.count)
        workers = rq.Worker.all(queue=q)
        if not workers:
            _update_cache(False, now)
            return False
    except Exception:
        pass  # fail-open for worker check

    _update_cache(True, now)
    return True
```

---

## Agent 4: agent-qa — 測試驗證

### 任務清單

| # | 任務 | 範圍 |
|---|------|------|
| QA1 | 跑既有測試套件確認無回歸 | `pytest tests/` |
| QA2 | 驗證新 `core/interactive_memory_guard.py` 單元測試 | 新測試 |
| QA3 | 驗證 Material Trace 快取行為（hit/miss/TTL） | `test_material_trace_*.py` |
| QA4 | 驗證 EventFetcher 截斷邏輯 | `test_event_fetcher.py` |
| QA5 | 驗證 RQ 健康檢查各場景（worker 存活/掉線/Redis 斷線） | `test_trace_job_service.py` |
| QA6 | 壓力測試：模擬高 CID 數量的記憶體用量 | `tests/stress/` |

---

## 執行順序與依賴

```
Week 1:
  Day 1-2: agent-shared (S1-S6)     ← 阻塞後續
  Day 2:   開始 agent-mt, agent-qt, agent-md (平行)

Week 1-2:
  agent-mt: MT1→MT2→MT3→MT4→MT5→MT6→MT7
  agent-qt: QT1→QT2→QT3→QT4→QT5→QT6→QT7→QT8
  agent-md: MD1→MD2→MD3→MD4→MD5→MD6→MD7

Week 2:
  agent-qa: QA1→QA6 (全部完成後)
```

---

## 風險與注意事項

1. **Material Trace Redis 快取需要 `core/redis_df_store.py`** — 已被 equipment_status_hours 使用，API 可直接沿用
2. **EventFetcher 截斷會影響中段缺陷** — mid-section defect 的 events 也走 EventFetcher，需確保截斷標記正確傳遞
3. **SQL OFFSET/FETCH 需要 Oracle 12c+** — 確認生產環境版本支援
4. **RQ worker 檢查有效能開銷** — 使用 60s TTL cache 避免每次請求都查
