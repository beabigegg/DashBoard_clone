## 1. Feature flag 基礎設施

- [x] 1.1 在 `reject_dataset_cache.py` 頂層加入 `_PHASE2_METADATA_ONLY: bool = os.getenv("PHASE2_METADATA_ONLY", "1") == "1"`
- [x] 1.2 在 `hold_dataset_cache.py` 頂層加入同樣的 flag 讀取
- [x] 1.3 在 `resource_dataset_cache.py` 頂層加入同樣的 flag 讀取

## 2. reject_dataset_cache.py — 直連路徑改為 spool

- [x] 2.1 在 import 區塊確認 `store_spooled_df` 已從 `query_spool_store` 匯入（已有 `register_spool_file`，補上 `store_spooled_df` 若缺少）
- [x] 2.2 修改 `_store_df(query_id, df)`：flag=1 時呼叫 `store_spooled_df(_REDIS_NAMESPACE, query_id, df, ttl_seconds=_CACHE_TTL)`，flag=0 時保留 `_redis_store_df(query_id, df)`
- [x] 2.3 修改 `_load_df_on_demand(query_id)`（L1 miss 的讀取路徑）：flag=1 時 primary path 改為 `load_spooled_df(_REDIS_NAMESPACE, query_id)`；保留 `redis_load_df()` 作為過渡 fallback（僅在 spool miss 時嘗試）
- [x] 2.4 確認 engine 路徑（`_store_query_result()`）不受 flag 影響，行為保持不變

## 3. hold_dataset_cache.py — 直連路徑改為 spool

- [x] 3.1 在 import 區塊確認 `store_spooled_df`, `load_spooled_df` 已匯入 `query_spool_store`（確認 `register_spool_file` 與 `load_spooled_df` 是否已有）
- [x] 3.2 修改 `_store_df(query_id, df)`：flag=1 時呼叫 `store_spooled_df`，flag=0 保留 `_redis_store_df`
- [x] 3.3 修改 `_get_cached_df(query_id)` 的 L2 讀取路徑：flag=1 時先 `load_spooled_df`，再 Redis fallback；flag=0 維持原邏輯（Redis first → spool fallback）
- [x] 3.4 確認 engine 路徑（`register_spool_file` 呼叫點）不受 flag 影響

## 4. resource_dataset_cache.py — 直連路徑改為 spool

- [x] 4.1 在 import 區塊確認 `store_spooled_df`, `load_spooled_df` 已匯入
- [x] 4.2 修改 `_store_df(query_id, df)`：flag=1 時呼叫 `store_spooled_df`，flag=0 保留 `_redis_store_df`
- [x] 4.3 修改 `_get_cached_df(query_id)`：flag=1 時先 `load_spooled_df`，再 Redis fallback；flag=0 維持原邏輯
- [x] 4.4 確認 engine 路徑（`register_spool_file` 呼叫點）不受 flag 影響

## 5. 測試更新

- [x] 5.1 更新 `test_reject_dataset_cache.py`（若存在）：mock `store_spooled_df`，確認 `redis_store_df` 不被呼叫（`PHASE2_METADATA_ONLY=1` 時）
- [x] 5.2 更新 `test_hold_dataset_cache.py`（若存在）：同上
- [x] 5.3 更新 `test_resource_dataset_cache.py`（若存在）：同上
- [x] 5.4 新增 fallback scenario 測試：spool miss 時確認 `redis_load_df()` 被嘗試
- [x] 5.5 新增 flag=0 regression 測試：確認舊路徑 `redis_store_df` 仍被呼叫

## 6. Validation

- [x] 6.1 執行 `pytest tests/ -v` 確認現有測試全數通過（含 Phase 1 baseline，允許 2 個 pre-existing TestWarmupTasks 失敗）
- [ ] 6.2 確認 `PHASE2_METADATA_ONLY=0` 啟動後，reject/hold/resource 仍正常寫入 Redis（手動測試或整合測試）
- [ ] 6.3 確認 `PHASE2_METADATA_ONLY=1`（預設）啟動後，查詢結果可由 spool 正確讀回（smoke test：執行一次查詢，重啟後再次 apply_view 成功）
- [ ] 6.4 確認 Redis `reject_dataset:*`, `hold_dataset:*`, `resource_dataset:*` 大型 payload key 在 TTL 後消失（`redis-cli keys` 驗證）
