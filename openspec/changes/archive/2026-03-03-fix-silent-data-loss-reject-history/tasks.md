## 1. 前端日期範圍即時驗證

- [x] 1.1 在 `frontend/src/core/reject-history-filters.js` 末尾新增 `validateDateRange(startDate, endDate)` 函式（MAX_QUERY_DAYS=730），回傳空字串表示通過、非空字串為錯誤訊息
- [x] 1.2 在 `frontend/src/reject-history/App.vue` import `validateDateRange`，在 `executePrimaryQuery()` 的 API 呼叫前（`errorMessage.value = ''` 重置之後）加入 date_range 模式的驗證邏輯，驗證失敗時設定 `errorMessage` 並 return

## 2. 後端追蹤失敗 chunk 時間範圍

- [x] 2.1 在 `batch_query_engine.py` 的 `_update_progress()` 簽名加入 `failed_ranges: Optional[List] = None` 參數，在 mapping dict 中條件性加入 `json.dumps(failed_ranges)` 欄位
- [x] 2.2 在 `execute_plan()` 的 sequential path（`for idx, chunk in enumerate(chunks)` 迴圈區段）新增 `failed_range_list = []`，chunk 失敗時從 chunk descriptor 條件性提取 `chunk_start`/`chunk_end` append 到 list（僅 time-range chunk 才有），傳入每次 `_update_progress()` 呼叫
- [x] 2.3 在 `_execute_parallel()` 修改 `futures` dict 為 `futures[future] = (idx, chunk)` 以保留 chunk descriptor，新增 `failed_range_list`，失敗時條件性 append range，返回值改為 4-tuple `(completed, failed, has_partial_failure, failed_range_list)`；同步更新 `execute_plan()` 中呼叫 `_execute_parallel()` 的解構為 4-tuple

## 3. 後端 chunk 失敗單次重試

- [x] 3.1 在 `batch_query_engine.py` 新增 `_RETRYABLE_PATTERNS` 常數和 `_is_retryable_error(exc)` 函式，辨識 Oracle timeout / 連線錯誤
- [x] 3.2 修改 `_execute_single_chunk()` 加入 `max_retries: int = 1` 參數，將 try/except 包在 retry loop 中：memory guard 和 Redis store 失敗直接 return False 不重試；exception 中若 `_is_retryable_error()` 為 True 則 log warning 並 continue

## 4. 後端傳遞 partial failure 到 API response

- [x] 4.1 在 `reject_dataset_cache.py` 的 `execute_primary_query()` 內 batch_query_engine local import 區塊加入 `get_batch_progress`
- [x] 4.2 在 `execute_primary_query()` 的 `merge_chunks()` 呼叫之後、`redis_clear_batch()` 呼叫之前，呼叫 `get_batch_progress("reject", engine_hash)` 讀取 `has_partial_failure`、`failed`、`failed_ranges`
- [x] 4.3 在 `redis_clear_batch()` 之後、`_apply_policy_filters()` 之前，將 partial failure 資訊條件性注入 `meta` dict（`has_partial_failure`、`failed_chunk_count`、`failed_ranges`）
- [x] 4.4 新增 `_store_partial_failure_flag(query_id, failed_count, failed_ranges, ttl)` 和 `_load_partial_failure_flag(query_id)` 兩個 helper，使用 Redis HSET 存取 `reject_dataset:{query_id}:partial_failure`；`ttl` 由呼叫端傳入
- [x] 4.5 在 `_store_query_result()` 呼叫之後呼叫 `_store_partial_failure_flag()`，TTL 根據 `_store_query_result()` 內的 `should_spill` 判斷：spill 到 spool 時用 `_REJECT_ENGINE_SPOOL_TTL_SECONDS`（21600s），否則用 `_CACHE_TTL`（900s）；在 `_get_cached_df()` cache-hit 路徑呼叫 `_load_partial_failure_flag()` 並 `meta.update()`

## 5. 前端 partial failure 警告 banner

- [x] 5.1 在 `frontend/src/reject-history/App.vue` 新增 `partialFailureWarning` ref，在 `executePrimaryQuery()` 開頭重置，在讀取 result 後根據 `result.meta.has_partial_failure` 設定警告訊息（含 failed_ranges 的日期區間文字；無 ranges 時用 failed_chunk_count 的 generic 訊息）
- [x] 5.2 在 App.vue template 的 error-banner `<div>` 之後加入 `<div v-if="partialFailureWarning" class="warning-banner">{{ partialFailureWarning }}</div>`
- [x] 5.3 在 `frontend/src/reject-history/style.css` 的 `.error-banner` 規則之後加入 `.warning-banner` 樣式（background: #fffbeb, color: #b45309）

## 6. 測試

- [x] 6.1 在 `tests/test_batch_query_engine.py` 新增 `test_transient_failure_retried_once`：mock query_fn 第一次 raise TimeoutError、第二次成功，assert chunk 最終成功且 query_fn 被呼叫 2 次
- [x] 6.2 在 `tests/test_batch_query_engine.py` 新增 `test_memory_guard_not_retried`：mock query_fn 回傳超大 DataFrame，assert query_fn 僅被呼叫 1 次
- [x] 6.3 在 `tests/test_batch_query_engine.py` 新增 `test_failed_ranges_tracked`：3 chunks 其中 1 個失敗，assert Redis metadata 含 `failed_ranges` JSON
- [x] 6.4 在 `tests/test_reject_dataset_cache.py` 新增 `test_partial_failure_in_response_meta`：mock `get_batch_progress` 回傳 `has_partial_failure=True`，assert response `meta` 包含旗標和 `failed_ranges`
- [x] 6.5 在 `tests/test_reject_dataset_cache.py` 新增 `test_cache_hit_restores_partial_failure`：先寫入 partial failure flag，cache hit 時 assert meta 有旗標
- [x] 6.6 在 `tests/test_reject_dataset_cache.py` 新增 `test_partial_failure_ttl_matches_spool`：當 should_spill=True 時 assert flag TTL 為 `_REJECT_ENGINE_SPOOL_TTL_SECONDS`，否則為 `_CACHE_TTL`
- [x] 6.7 在 `tests/test_batch_query_engine.py` 新增 `test_id_batch_chunk_no_failed_ranges`：container-id 分塊 chunk 失敗時 assert `failed_ranges` 為空 list 但 `has_partial_failure=True`

## 7. 跨服務回歸驗證

- [x] 7.1 執行 `pytest tests/test_batch_query_engine.py tests/test_reject_dataset_cache.py -v` 確認本次修改的測試全部通過
- [x] 7.2 執行 hold_dataset_cache 相關測試確認重試邏輯不影響 hold：`pytest tests/ -k "hold" -v`
- [x] 7.3 執行 resource / job / msd 相關測試確認回歸：`pytest tests/ -k "resource or job or mid_section" -v`
- [x] 7.4 若任何跨服務測試失敗，檢查是否為 `_execute_single_chunk` 簽名變更（`max_retries` 參數）導致，確認 keyword-only 預設值不影響既有呼叫
