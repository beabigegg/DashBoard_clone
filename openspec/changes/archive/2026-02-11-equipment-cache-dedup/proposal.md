## Why

`.env` 設定 `GUNICORN_WORKERS=4`，每個 worker 各自有獨立的 equipment sync thread（共 4 個）。每 5 分鐘週期，4 個 sync thread 輪流取得分散式鎖後都去查 Oracle，產生 4 次完全相同的 `SELECT ... FROM DW_MES_EQUIPMENTSTATUS_WIP_V`（~2700 rows），其中 3 次是多餘的。分散式鎖只做序列化（serialize），沒有去重（deduplicate）。另外 `init_realtime_equipment_cache()` 存在 double-call 問題：init 先呼叫一次 `refresh_equipment_status_cache()`，再啟動 sync thread 立即又呼叫一次。

## What Changes

- **Freshness gate**：`refresh_equipment_status_cache()` 取得分散式鎖後、查 Oracle 前，檢查 Redis `equipment_status:meta:updated` 時間戳。若距上次更新不到 `sync_interval / 2` 秒，跳過 Oracle 查詢並釋放鎖。`force=True` 繞過此檢查。
- **Wait-first sync worker**：`_sync_worker()` 改為先等 interval 再開始查詢（`_STOP_EVENT.wait(timeout=interval)` loop），避免與 init 的首次 refresh 重複。
- **模組級 `_SYNC_INTERVAL` 變數**：由 `init_realtime_equipment_cache()` 設定，供 freshness gate 使用。

## Capabilities

### New Capabilities

（無新增 capability。此為既有 equipment cache sync 機制的去重優化。）

### Modified Capabilities

（無 spec-level requirement 變更。改動純屬實作層最佳化，不影響快取對外行為、資料即時性或 API 契約。）

## Impact

- **檔案**：`src/mes_dashboard/services/realtime_equipment_cache.py`（唯一修改檔案）
- **Oracle 負載**：每 5 分鐘週期從 4 次查詢降至 1 次
- **資料即時性**：無影響，每週期仍保證至少 1 次更新
- **`force=True` 調用**：無影響，繞過 freshness gate
- **Process-level cache**：無影響，`_save_to_redis()` 已呼叫 `invalidate()`，其他 worker 的 L1 cache 在 30s TTL 內自然過期
- **Worker 重啟（gunicorn max_requests）**：改善——新 worker 的 init refresh 會被 freshness gate 擋住
