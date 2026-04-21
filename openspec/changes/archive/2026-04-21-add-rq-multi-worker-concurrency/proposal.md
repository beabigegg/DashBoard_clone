## Why

生產環境部署多個 RQ worker process（共用單一 Redis 容器）。現有測試 [tests/test_rq_worker_crash_recovery.py](tests/test_rq_worker_crash_recovery.py) 僅涵蓋單 worker SIGKILL 恢復情境；既有 spec `cross-worker-result-integrity` 與 `async-job-stress-probe` 規範了結果可見性與 queue saturation，但缺少明確的「多 worker 同時競爭資源」的測試。

實際多 worker 風險情境（job 重複執行、export 去重競爭、stale lock、result write/read race、queue 飢餓）若未經測試保證，將在尖峰時段引發資料重複、丟失或卡死，且問題難以本地重現。本變更建立「多 worker 併發測試」覆蓋面，將上述風險變成可重現的回歸測試。

## What Changes

- 新增 `tests/integration/test_multi_worker_concurrency.py`，啟動 2-3 個 RQ worker subprocess 共用 Redis，覆蓋下列場景：
  - **Job 冪等**：worker A 拿到 job 後 SIGKILL，worker B 接手 → 同 job 不應產生重複副作用
  - **Export 去重競爭**：兩 worker 同時收到相同 fingerprint 的 export request → 僅執行一次，另一者讀 cache
  - **Stale lock 復原**：lock holder crash 後，TTL 內其他 worker 不搶鎖；TTL 到期後新 contender 能取得鎖
  - **Result write/read race**：A 寫 result 同時 B 讀 → B 看到完整舊值或完整新值，不見半寫入
  - **Queue 公平性**：N workers 拉同一 queue 的 M jobs (M >> N) → 每個 worker 至少被分到一個 job，無永久飢餓
- 新增測試輔助 `tests/integration/_multi_worker_harness.py`：管理 worker subprocess 生命週期、收集 worker log、清理 Redis state
- 新增 pytest marker `@pytest.mark.multi_worker`，CI 中以獨立 job 執行（避免影響單元測試速度）
- 不修改 production 程式碼（純測試補強）；若測試暴露現有實作缺陷，於後續變更獨立修復

## Capabilities

### New Capabilities
- `multi-worker-concurrency-test-coverage`: 規範多 RQ worker 併發測試的場景、harness 設計、執行策略與通過標準

### Modified Capabilities
（無——本變更只新增測試覆蓋，不改既有 spec 的需求）

## Impact

- **依賴**：無新增（沿用現有 `rq`、`redis`、`pytest`）
- **測試**：新增 `tests/integration/test_multi_worker_concurrency.py` 與 `_multi_worker_harness.py`
- **CI**：需配置可啟動多個 worker subprocess 的 CI runner；預估執行時間 +60-120s（含 worker 啟停與 Redis 清理）
- **風險**：測試本身對 timing 敏感；harness 需提供確定性的同步機制（barrier / event）避免 flaky
- **不影響**：production 程式碼、API 契約、前端
