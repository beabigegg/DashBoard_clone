## Context

報廢歷史查詢使用 `BatchQueryEngine` 將長日期範圍拆成 10 天 chunks 平行查詢 Oracle。每個 chunk 有記憶體上限（256 MB）和 timeout（300s）防護。當 chunk 失敗時，`has_partial_failure` 旗標寫入 Redis HSET（key: `batch:reject:{hash}:meta`），但此資訊**在三個斷點被丟失**：

1. `reject_dataset_cache.py` 的 `execute_primary_query()` 未讀取 batch progress metadata
2. API route 直接 `jsonify({"success": True, **result})`，在 partial chunk failure 路徑下仍回 HTTP 200 + `success: true`，不區分完整與不完整結果
3. 前端 `App.vue` 沒有任何 partial failure 處理邏輯

另一個問題：`redis_clear_batch()` 在 `execute_primary_query()` 的清理階段會刪除 metadata key，所以讀取必須在清理之前。

前端的 730 天日期上限驗證只在後端 `_validate_range()` 做，前端缺乏即時回饋。

## Goals / Non-Goals

**Goals:**

- 將 `has_partial_failure` 從 Redis metadata 傳遞到 API response `meta` 欄位
- 追蹤失敗 chunk 的時間範圍，讓前端可顯示具體的缺漏區間
- 前端顯示 amber warning banner，告知使用者資料可能不完整
- 前端加入日期範圍即時驗證，避免無效 API 請求
- 對 transient error（Oracle timeout、連線失敗）加入單次重試，減少不必要的 partial failure
- 持久化 partial failure 旗標到獨立 Redis key，讓 cache-hit 路徑也能還原警告狀態

**Non-Goals:**

- 不改變現有 chunk 分片策略或記憶體上限數值
- 不實作前端的自動重查/重試機制
- 不修改 `EVENT_FETCHER_ALLOW_PARTIAL_RESULTS` 的行為（預設已是安全的 false）
- 不加入 progress bar / 即時進度追蹤 UI

## Decisions

### D1: 在 `redis_clear_batch` 之前讀取 metadata

**決定**: 在 `execute_primary_query()` 中，`merge_chunks()` 之後、`redis_clear_batch()` 之前，呼叫 `get_batch_progress("reject", engine_hash)` 讀取 partial failure 狀態。

**理由**: `redis_clear_batch` 會刪除包含 metadata 的 key，之後就讀不到了。此時 chunk 資料已合併完成，是最後可讀取 metadata 的時機點。

### D2: 用獨立 Redis key 持久化 partial failure flag，TTL 對齊實際資料層

**決定**: 在 `_store_query_result()` 之後，將 partial failure 資訊存到 `reject_dataset:{query_id}:partial_failure` Redis HSET。**TTL 必須與資料實際存活的層一致**：若資料 spill 到 parquet spool（`_REJECT_ENGINE_SPOOL_TTL_SECONDS = 21600s`），partial failure flag 的 TTL 也要用 21600s；若資料存在 L1/L2（`_CACHE_TTL = 900s`），flag TTL 用 900s。實作方式：`_store_partial_failure_flag()` 接受 `ttl` 參數，由呼叫端根據 `should_spill` 判斷傳入 `_REJECT_ENGINE_SPOOL_TTL_SECONDS` 或 `_CACHE_TTL`。Cache-hit 路徑透過 `_load_partial_failure_flag(query_id)` 還原。

**替代方案 A**: 將 flag 嵌入 DataFrame 的 attrs 或另外 pickle。
**為何不採用**: DataFrame attrs 在 parquet 序列化時會丟失；pickle 增加反序列化風險。

**替代方案 B**: 固定 TTL=900s。
**為何不採用**: 大查詢 spill 到 parquet spool（21600s TTL），資料還能讀 6 小時，但 partial failure flag 15 分鐘就過期，造成「資料讀得到但警告消失」。

### D3: 在 `_update_progress` 中追蹤 failed_ranges（僅 time-range chunk）

**決定**: 擴充 `_update_progress()` 接受 `failed_ranges: Optional[List[Dict]]` 參數，以 JSON 字串存入 Redis HSET。Sequential 和 parallel path 均從失敗的 chunk descriptor 提取 `chunk_start` / `chunk_end`。**僅當 chunk descriptor 包含 `chunk_start`/`chunk_end` 時才記錄**（即 `decompose_by_time_range` 產生的 time-range chunk）。

**container-id 分塊的情境**: reject 的 container 模式使用 `decompose_by_ids()`，chunk 結構為 `{"ids": [...]}` 不含日期範圍。此時 `failed_ranges` 為空 list，前端透過 `failed_chunk_count > 0` 顯示 generic 警告訊息（「N 個查詢批次的資料擷取失敗」），不含日期區間。

**理由**: chunk descriptor 的結構由 decompose 函式決定，engine 層不應假設所有 chunk 都有時間範圍。

### D4: Memory guard 失敗不重試

**決定**: `_execute_single_chunk()` 加入 `max_retries=1`，但只對 `_is_retryable_error()` 回傳 true 的 exception 重試。Memory guard（記憶體超限）和 Redis store 失敗直接 return False，不重試。

**理由**: Memory guard 代表該時段資料量確實過大，重試結果相同；Oracle timeout 和連線錯誤則可能是暫態問題。

### D5: 前端 warning banner 使用既有 amber 色系

**決定**: 新增 `.warning-banner` CSS class，使用 `background: #fffbeb; color: #b45309`，與既有 `.resolution-warn` 的 amber 色系一致。放在 `.error-banner` 之後。

**替代方案**: 使用 toast/notification 元件。
**為何不採用**: 此專案無 toast 系統，amber banner 與 red error-banner 模式統一。

### D6: 前端日期驗證函式放在共用 filters module

**決定**: 在 `frontend/src/core/reject-history-filters.js` 新增 `validateDateRange()`，複用 `resource-history/App.vue:231-248` 的驗證模式。

**理由**: reject-history-filters.js 已是此頁面的 filter 工具模組，validateDateRange 屬於 filter 驗證邏輯。

## Risks / Trade-offs

- **[中] 重試邏輯影響所有 execute_plan 呼叫端** — `_execute_single_chunk()` 是 shared function，被 reject / hold / resource / job / msd 五個服務共用。重試邏輯為加法行為（新增 retry loop 包在既有 try/except 外），成功路徑不變。→ 需要對其他 4 個服務執行 smoke test（既有測試通過即可）。若需更保守，可加入 `max_retries` 參數讓呼叫端控制（預設 1），但目前判斷統一重試對所有服務都是正面效果。
- **[低] 重試增加 Oracle 負擔** — 單次重試最多增加 1 倍的失敗查詢量。→ 透過 `_is_retryable_error()` 嚴格過濾，只重試 transient error，且 parallel path 最多 3 worker，影響可控。
- **[低] failed_ranges JSON 大小** — 理論上 73 chunks（730/10）全部失敗會產生 73 筆 range，JSON < 5 KB。→ 遠低於 Redis HSET 欄位限制。
