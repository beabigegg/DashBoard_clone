## Context

### 現況

「設備歷史績效」採兩段式查詢流程：

```
POST /query
  → try_compute_query_from_canonical_spool()   ← 優先走 canonical spool
      ↓ miss
  → execute_primary_query()
      ├─ should_decompose_by_time?
      │    YES (>10 天) → execute_plan(base, parallel=1) → merge_chunks_to_spool
      │                  → execute_plan(oee,  parallel=1) → merge_chunks_to_spool
      │    NO            → ThreadPoolExecutor(2): base + oee 並行
      └─ apply_view() → DuckDB → response
```

### 關鍵問題（量化）

| 問題 | 數字 |
|------|------|
| Spool TTL | 900 秒（15 分鐘） |
| Warmup 間隔 | 3600 秒（60 分鐘） |
| Spool 冷機率 | **75%**（每小時 45 分鐘沒 spool） |
| 長查詢（90天）Oracle 次數 | base 3 次 + oee 3 次 = **6 次串行** |
| execute_plan parallel 預設 | **1**（全專案 hardcoded，無 env 管理） |
| partial failure 靜默率 | 5/6 服務完全不讀 execute_plan 失敗結果 |

### 受影響服務

- **resource_dataset_cache** — TTL、parallel、partial failure
- **hold_dataset_cache** — parallel、partial failure
- **job_query_service** — parallel、partial failure
- **production_history_service** — parallel（explicit `parallel=1`）、partial failure
- **mid_section_defect_service** — parallel、partial failure
- **reject_dataset_cache** — 已有 `REJECT_ENGINE_PARALLEL` env var，但 partial failure 未傳到 API response

---

## Goals / Non-Goals

**Goals:**
- 修正 TTL vs warmup 不匹配，消除 75% 冷機率
- 所有重查詢服務的 `parallel` 改為 env var 管理，預設維持 1（安全），允許調高
- `execute_plan` partial failure（含 OOM 靜默丟棄）必須傳遞到 response `_meta`，使告警可觀察
- 不破壞任何現有 API contract 或 response shape

**Non-Goals:**
- OEE SQL ±30 天 reject 窗口的修改（業務語意正確，不在本次範圍）
- base + oee 分片的跨類型並行（長查詢路徑，屬獨立優化，不在本次範圍）
- warmup 窗口擴展（獨立 scope）
- frontend 顯示 partial failure 警告（後端先補齊，前端整合另立 change）

---

## Decisions

### D1：TTL 拉長策略

**決策：** 為 `CACHE_TTL_DATASET` 加 env var，並把預設值從 900 提高到 **7200 秒（2 小時）**。

**理由：**
- 設備歷史績效是歷史資料（班次狀態），2 小時內不會有業務語意上的變化
- 7200 > 3600（warmup 間隔），確保 warmup 補充前 spool 仍有效
- Parquet 檔案本來就在磁碟上；TTL 只控制 Redis metadata pointer 的存活，提高 TTL 不增加磁碟壓力
- hold/reject 共用同一個 `CACHE_TTL_DATASET`——hold 資料同樣是歷史資料，2 小時可接受

**替代方案考量：**
- *降低 warmup 間隔到 < 900 秒*：warmup 每 15 分鐘跑一次代價過高，且仍有競態視窗
- *分離 resource 與 hold/reject 的 TTL*：增加常數複雜度，目前無必要
- *TTL 改為 3600*（等於 warmup 間隔）：有競態（warmup 延遲時仍會短暫冷），7200 更保守

**實作：**

```python
# constants.py
CACHE_TTL_DATASET = int(os.getenv("CACHE_TTL_DATASET_SECONDS", "7200"))
```

---

### D2：Parallel env var 統一化

**決策：** 為各服務加獨立 env var，預設 1（維持現有行為），允許運維按需調高。

**理由：**
- `_effective_parallelism()` 已有 hard ceiling（min(requested, 3)）及 semaphore 保護（`DB_SLOW_MAX_CONCURRENT`），調高 parallel 不會失控
- 各服務資料量差異大（resource base 單 chunk ~5 MB vs reject primary 可達 100+ MB），應允許各自獨立調整
- `reject_dataset_cache` 已有此模式（`REJECT_ENGINE_PARALLEL`），本次統一其他服務比照

**Env var 命名規範：** `{SERVICE}_ENGINE_PARALLEL`

| 服務 | Env var | 預設 |
|------|---------|------|
| resource_dataset_cache | `RESOURCE_ENGINE_PARALLEL` | 1 |
| hold_dataset_cache | `HOLD_ENGINE_PARALLEL` | 1 |
| job_query_service | `JOB_ENGINE_PARALLEL` | 1 |
| production_history_service | `PRODUCTION_ENGINE_PARALLEL` | 1 |
| mid_section_defect_service | `MSD_ENGINE_PARALLEL` | 1 |

**實作位置：** 各服務 module 頂層（比照 reject 的 `_REJECT_ENGINE_PARALLEL = max(1, int(os.getenv(...)))` 模式），並在呼叫 `execute_plan` 時傳入。

**替代方案考量：**
- *單一全域 env var*：無法應對各服務資料量差異，且有些服務（production_history）更保守，不應被一起調高

---

### D3：Partial failure 傳遞

**決策：** 讀取 `execute_plan` 後的 Redis progress metadata，若有 `has_partial_failure` 則在 response `_meta` 帶出，讓 log 與監控可見。不在本次更改 frontend。

**問題根因：**
- `execute_plan` 回傳 `query_hash`（str）；失敗資訊在 Redis progress key 裡，需呼叫 `get_batch_progress()` 才能取得
- 全部 6 個服務都未讀取，導致 OOM chunk 丟棄完全靜默

**傳遞路徑：**

```
execute_plan(...)
get_batch_progress(cache_prefix, query_hash)  ← 新增
  → has_partial_failure=True?
      → 帶入 result["_meta"]["partial_failure"] = { failed_chunk_count, failed_ranges }
      → logger.warning(...)  ← 讓 Gunicorn log 可見
```

**決策：response shape 不改變**，partial failure 只放在現有的 `_meta` dict 內（已是 internal field），不影響 API contract。

**reject 特殊處理：** `reject_dataset_cache` 已有 `_store_partial_failure_flag` 機制且更完整，本次只補其 API response 傳遞部分（確保 `_meta` 帶出），不重構其現有邏輯。

---

## Risks / Trade-offs

| 風險 | 緩解措施 |
|------|---------|
| TTL 拉長後資料略舊（最多 2 小時） | 設備歷史績效為歷史報表，使用者預期的是「今天早上的數據」，2 小時可接受；如需更即時可調低 env var |
| parallel 調高後 Oracle 連線壓力 | `_effective_parallelism()` hard ceiling=3 + `DB_SLOW_MAX_CONCURRENT` semaphore 雙重保護已存在；預設值維持 1，不自動調高 |
| partial failure log 噪音 | 僅在 `has_partial_failure=True` 時發 WARNING，正常路徑無噪音 |
| CACHE_TTL_DATASET 共用於 hold/reject，拉長可能影響資料即時性 | hold/reject 同為歷史資料，2 小時無業務問題；如需差異化，後續可拆分常數 |

---

## Migration Plan

1. **constants.py** — `CACHE_TTL_DATASET` 加 `os.getenv`，預設 7200
2. **resource_dataset_cache.py** — 加 `RESOURCE_ENGINE_PARALLEL` env var，傳入兩個 `execute_plan` call；補 partial failure 讀取
3. **hold_dataset_cache.py** — 加 `HOLD_ENGINE_PARALLEL` env var；補 partial failure
4. **job_query_service.py** — 加 `JOB_ENGINE_PARALLEL` env var；補 partial failure
5. **production_history_service.py** — 加 `PRODUCTION_ENGINE_PARALLEL` env var（移除 explicit `parallel=1`）；補 partial failure
6. **mid_section_defect_service.py** — 加 `MSD_ENGINE_PARALLEL` env var；補 partial failure
7. **reject_dataset_cache.py** — 補 partial failure 到 response `_meta`（其 env var 已存在）

**部署順序：** 所有改動純加法（env var + log），可一次性部署，無需 migration 腳本或停機。

**Rollback：** 刪除 env var 或設回舊值即可；TTL 改動重啟服務後立即生效。

---

## Open Questions

- `PRODUCTION_ENGINE_PARALLEL`：production_history 是 LOT 級資料，單 chunk 可能最大，應建議預設維持 1 且文件說明不建議調超過 2。是否在 code 加額外 cap？→ 暫不加，`_effective_parallelism()` 的 hard ceiling=3 已足夠
- partial failure 是否應讓 warmup 自動重試？→ 不在本次範圍，warmup 本身有 RQ job timeout 保護
