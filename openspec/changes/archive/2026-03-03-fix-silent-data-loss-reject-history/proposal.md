## Why

報廢歷史查詢的防爆機制（時間分片 + 記憶體上限 256 MB + Oracle timeout 300s）在 chunk 失敗時會丟棄該 chunk 的資料，`has_partial_failure` 旗標僅寫入 Redis metadata，**從未傳遞到 API response 或前端**。使用者查到不完整資料卻毫不知情，影響決策正確性。此外，730 天日期上限僅在後端驗證，前端無即時提示，導致不必要的等待。

## What Changes

- 後端 `reject_dataset_cache` 在 `execute_plan()` 後讀取 batch progress metadata，將 `has_partial_failure`、失敗 chunk 數量及失敗時間範圍注入 API response `meta` 欄位
- 後端 `batch_query_engine` 追蹤失敗 chunk 的時間區間描述，寫入 Redis metadata 的 `failed_ranges` 欄位
- 後端 `_execute_single_chunk()` 對 transient error（Oracle timeout / 連線錯誤）加入單次重試，memory guard 失敗不重試
- 前端新增 amber warning banner，當 `meta.has_partial_failure` 為 true 時顯示不完整資料警告及失敗的日期區間
- 前端新增日期範圍即時驗證（730 天上限），在 API 發送前攔截無效範圍

## Capabilities

### New Capabilities

- `batch-query-resilience`: 批次查詢引擎的失敗範圍追蹤、partial failure metadata 傳遞、及 transient error 單次重試機制

### Modified Capabilities

- `reject-history-api`: API response `meta` 新增 `has_partial_failure`、`failed_chunk_count`、`failed_ranges` 欄位，讓前端得知查詢結果完整性
- `reject-history-page`: 新增 amber warning banner 顯示 partial failure 警告；新增前端日期範圍即時驗證（730 天上限）

## Impact

- **後端服務 — batch_query_engine.py（共用模組，影響所有使用 execute_plan 的服務）**:
  - 追蹤 failed_ranges + 重試邏輯修改的是 `_execute_single_chunk()`，此函式被 **reject / hold / resource / job / msd** 五個 dataset cache 服務共用
  - 重試邏輯為加法行為（新增 retry loop），不改變既有成功路徑，對其他服務向後相容
  - `failed_ranges` 追蹤僅在 chunk descriptor 含 `chunk_start`/`chunk_end` 時才記錄，container-id 分塊（僅 reject container 模式使用）不受影響
  - 需對 hold / resource / job / msd 執行回歸 smoke test
- **後端服務 — reject_dataset_cache.py**: 讀取 metadata + 注入 response + 持久化 partial failure flag
- **前端**: `App.vue`（warning banner + 日期驗證）、`reject-history-filters.js`（validateDateRange 函式）、`style.css`（.warning-banner 樣式）
- **API 契約**: response `meta` 新增可選欄位（向後相容，現有前端不受影響）
- **測試**: `test_batch_query_engine.py`、`test_reject_dataset_cache.py` 需新增對應測試案例；hold / resource / job / msd 需回歸驗證
