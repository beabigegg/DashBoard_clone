## 1. TTL 環境變數化（constants.py）

- [x] 1.1 在 `src/mes_dashboard/config/constants.py` 將 `CACHE_TTL_DATASET` 改為 `int(os.getenv("CACHE_TTL_DATASET_SECONDS", "7200"))`
- [x] 1.2 確認 `constants.py` 頂部已 import `os`（或使用 `_os`）
- [x] 1.3 驗證 `resource_dataset_cache._CACHE_TTL`、`hold_dataset_cache._CACHE_TTL`、`reject_dataset_cache._CACHE_TTL` 均沿用此常數無需修改

## 2. Resource dataset cache — parallel env var + partial failure

- [x] 2.1 在 `resource_dataset_cache.py` 頂層加 `_RESOURCE_ENGINE_PARALLEL = max(1, int(os.getenv("RESOURCE_ENGINE_PARALLEL", "1")))`
- [x] 2.2 在 `execute_primary_query()` 的 base `execute_plan(...)` call 加 `parallel=_RESOURCE_ENGINE_PARALLEL`
- [x] 2.3 在 `execute_primary_query()` 的 OEE `execute_plan(...)` call 加 `parallel=_RESOURCE_ENGINE_PARALLEL`
- [x] 2.4 在 base `execute_plan` 後呼叫 `get_batch_progress("resource", engine_hash)`，讀取 partial failure
- [x] 2.5 在 OEE `execute_plan` 後呼叫 `get_batch_progress("resource_oee", oee_engine_hash)`，合併 partial failure
- [x] 2.6 若有 partial failure，在 result dict 的 `_meta` 裡加入 `partial_failure` key，並 `logger.warning(...)` 帶出 failed_ranges
- [x] 2.7 確認 `get_batch_progress` 已從 `batch_query_engine` 正確 import

## 3. Hold dataset cache — parallel env var + partial failure

- [x] 3.1 在 `hold_dataset_cache.py` 頂層加 `_HOLD_ENGINE_PARALLEL = max(1, int(os.getenv("HOLD_ENGINE_PARALLEL", "1")))`
- [x] 3.2 在 `execute_plan(...)` call 加 `parallel=_HOLD_ENGINE_PARALLEL`
- [x] 3.3 在 `execute_plan` 後讀取 `get_batch_progress("hold", engine_hash)`，若有 partial failure 加入 result `_meta` 並 warning log

## 4. Job query service — parallel env var + partial failure

- [x] 4.1 在 `job_query_service.py` 頂層加 `_JOB_ENGINE_PARALLEL = max(1, int(os.getenv("JOB_ENGINE_PARALLEL", "1")))`
- [x] 4.2 在 `execute_plan(...)` call 加 `parallel=_JOB_ENGINE_PARALLEL`
- [x] 4.3 在 `execute_plan` 後讀取 `get_batch_progress("job", cache_hash)`，若有 partial failure 加入 result `_meta` 並 warning log

## 5. Production history service — parallel env var + partial failure

- [x] 5.1 在 `production_history_service.py` 頂層加 `_PRODUCTION_ENGINE_PARALLEL = max(1, int(os.getenv("PRODUCTION_ENGINE_PARALLEL", "1")))`
- [x] 5.2 移除 `execute_plan(...)` 中的 explicit `parallel=1`，改為 `parallel=_PRODUCTION_ENGINE_PARALLEL`
- [x] 5.3 在 `execute_plan` 後讀取 `get_batch_progress`（確認使用的 cache_prefix），若有 partial failure 加入 result 並 warning log

## 6. Mid-section defect service — parallel env var + partial failure

- [x] 6.1 在 `mid_section_defect_service.py` 頂層加 `_MSD_ENGINE_PARALLEL = max(1, int(os.getenv("MSD_ENGINE_PARALLEL", "1")))`
- [x] 6.2 在 `execute_plan(...)` call 加 `parallel=_MSD_ENGINE_PARALLEL`
- [x] 6.3 在 `execute_plan` 後讀取 `get_batch_progress("msd_detect", engine_hash)`，若有 partial failure 加入 result `_meta` 並 warning log

## 7. Reject dataset cache — partial failure 補傳到 response

- [x] 7.1 確認 `reject_dataset_cache.py` 的 primary query 路徑（已有 `_store_partial_failure_flag`），確認 partial failure 已被 propagate 到 response `meta` dict
- [x] 7.2 若 response 的 `meta` 中沒有帶出 `has_partial_failure`，補上讀取 `_load_partial_failure_flag(query_id)` 並合併至 meta
- [x] 7.3 確認有 `logger.warning(...)` 在 partial failure 時發出

## 8. Unit Tests — TTL env var

- [x] 8.1 在 `tests/test_resource_dataset_cache.py` 加 `TestCacheTTLEnvVar` class
- [x] 8.2 測試：`CACHE_TTL_DATASET_SECONDS` 未設定 → `constants.CACHE_TTL_DATASET == 7200`
- [x] 8.3 測試：`monkeypatch.setenv("CACHE_TTL_DATASET_SECONDS", "1800")` + module reload → `_CACHE_TTL == 1800`
- [x] 8.4 測試：`execute_primary_query()` 呼叫 `store_spooled_df` 時 `ttl_seconds` 等於 `_CACHE_TTL`

## 9. Unit Tests — parallel env var per service

- [x] 9.1 在 `tests/test_resource_dataset_cache.py` 加 `TestResourceEngineParallel` — 驗證 `RESOURCE_ENGINE_PARALLEL=2` 使兩個 `execute_plan` call 都帶 `parallel=2`；無 env var 時帶 `parallel=1`
- [x] 9.2 在 `tests/test_hold_dataset_cache.py` 加 `TestHoldEngineParallel` — 驗證 `HOLD_ENGINE_PARALLEL=2`
- [x] 9.3 在 `tests/test_job_query_service.py` 加 `TestJobEngineParallel` — 驗證 `JOB_ENGINE_PARALLEL=2`
- [x] 9.4 在 `tests/test_production_history_routes.py`（或新建 `test_production_history_service.py`）加 `TestProductionEngineParallel` — 驗證 `PRODUCTION_ENGINE_PARALLEL=2`，且原 hardcoded `parallel=1` 已被移除
- [x] 9.5 在 `tests/test_mid_section_defect_service.py` 加 `TestMsdEngineParallel` — 驗證 `MSD_ENGINE_PARALLEL=2`

## 10. Unit Tests — partial failure propagation

- [x] 10.1 在 `tests/test_resource_dataset_cache.py` 加 `TestResourcePartialFailure` class
- [x] 10.2 測試：base chunk partial failure → result `_meta["partial_failure"]["has_partial_failure"] == True`，且 `failed_ranges` 非空
- [x] 10.3 測試：OEE chunk partial failure → `_meta["partial_failure"]` 帶出 OEE 失敗資訊
- [x] 10.4 測試：所有 chunk 成功 → `_meta` 無 `partial_failure` key
- [x] 10.5 測試：partial failure 時有 `logger.warning` 被呼叫（用 `caplog` 或 `unittest.mock.patch`）
- [x] 10.6 在 `tests/test_hold_dataset_cache.py` 補 partial failure propagation 測試
- [x] 10.7 在 `tests/test_job_query_service.py` 補 partial failure propagation 測試
- [x] 10.8 在 production_history service 測試檔中補 partial failure propagation 測試
- [x] 10.9 在 `tests/test_mid_section_defect_service.py` 補 partial failure propagation 測試
- [x] 10.10 在 `tests/test_reject_dataset_cache.py` 補測試：確認 partial failure 出現在 API response `meta` 中

## 11. E2E Tests — resource-history spool reuse

- [x] 11.1 在 `tests/e2e/test_resource_history_e2e.py` 加 `TestResourceHistorySpoolReuse` class
- [x] 11.2 測試：兩次相同 POST /query，Oracle mock 只被呼叫一次（第二次走 spool）；兩次 response 的 `query_id` 相同
- [x] 11.3 測試：`try_compute_query_from_canonical_spool` 有 spool 時，response `query_id` 等於 canonical query_id，Oracle mock 未被呼叫

## 12. 回歸驗證

- [x] 12.1 跑 `pytest tests/ -v` 確認全部通過，無 regression
- [x] 12.2 跑 `pytest tests/e2e/ -v --run-integration`（若環境允許）確認 e2e 通過
- [x] 12.3 手動確認：server 重啟後 `CACHE_TTL_DATASET_SECONDS` 未設定時 log 顯示 `_CACHE_TTL=7200`
