## Context

生產部署使用多個 RQ worker process 共用單一 Redis 容器（單節點，無 Sentinel/Cluster）。現況：

- [tests/test_rq_worker_crash_recovery.py](tests/test_rq_worker_crash_recovery.py) 直接操作 Redis HSET 模擬 job state，**不啟動真實 worker subprocess**
- [tests/integration/test_race_conditions.py](tests/integration/test_race_conditions.py) 測單一 process 內的 thread-level 競爭
- spec `cross-worker-result-integrity` 與 `async-job-stress-probe` 規範了結果可見性與 queue saturation，但缺對應「兩個 RQ worker 同時搶 job / 鎖」的可重現測試

多 worker 真實風險（job 重複執行、export 去重競爭、stale lock 復原、result write/read race、queue 飢餓）目前依賴「單元測試 + 程式邏輯審視」，缺乏端到端證據。本變更新增整合測試啟動真實 RQ worker subprocess，覆蓋上述場景。

## Goals / Non-Goals

**Goals:**
- 建立可重現的多 worker 整合測試 harness（subprocess 管理、Redis 隔離、deterministic sync）
- 為 5 個關鍵風險情境寫測試：job 冪等、export 去重、stale lock、result race、queue 公平性
- 測試本身不依賴外部 Oracle / 真實 production 資料；以 mock job function 驗證併發語意
- CI 中以獨立 marker (`multi_worker`) 隔離執行，避免拖慢單元測試

**Non-Goals:**
- 不測 Redis 多節點 (Sentinel/Cluster) 行為——生產為單節點
- 不測 OS 層 IPC bug（subprocess fork/exec 由 stdlib 保證）
- 不取代既有 `test_rq_worker_crash_recovery.py`（保留作為 metadata-level 測試）
- 不重構 production worker / lock 程式碼；若測試暴露缺陷，於後續變更獨立修復

## Decisions

### 1. 啟動真實 worker subprocess vs. inproc fake worker
- **選擇 subprocess**：用 `subprocess.Popen` 啟動 `rq worker` 命令，連到測試專用 Redis db
- **理由**：inproc fake worker 無法測 process boundary 上的 race（檔案 lock、Redis pub/sub 跨 process 行為）
- **代價**：啟動時間 ~1-2s/worker，測試時間預期 +60-120s
- **替代方案**：用 `rq.SimpleWorker` 在 thread 內跑 → 無 process 隔離，違背測試目的

### 2. Redis 隔離：獨立 db index 而非獨立 container
- **選擇**：harness 使用 Redis db `15`（測試專用），測試前後 `FLUSHDB`
- **理由**：CI 已有 Redis service；多開 container 增加 CI 複雜度，db 隔離已足夠（單節點無 cross-db pollution）
- **替代方案**：testcontainers 起獨立 redis → CI 設定變動大、首版不採

### 3. 同步原語：Redis-based barrier，不用 sleep
- **設計**：harness 提供 `WorkerBarrier` 類，多個 worker 透過 Redis `INCR` + `BLPOP` 互相等待達到同步點
- **理由**：避免 flaky timing-dependent assertions；測試應斷言「事件順序」而非「時間長度」
- **替代方案**：用 `time.sleep(N)` → flaky、不確定 → 拒絕

### 4. Job function 設計：副作用記錄到 Redis list
- 測試用的 mock job function 將「執行了一次」、「執行 worker 的 PID」、「執行時間戳」`RPUSH` 到 Redis list
- 測試斷言透過 `LRANGE` 讀取此 list，驗證執行次數與順序
- **理由**：跨 process 觀察副作用最簡單可靠的方式

### 5. Worker 數量：固定 3 個
- **理由**：1 = 無併發、2 = 可測競爭、3 = 可測「2 個競爭時第 3 個的飢餓行為」；再多無新訊號
- **可調**：harness 接受 `worker_count` 參數，預設 3

### 6. Cleanup 策略：fixture-scoped, autouse, finalizer
- 每個測試 fixture 自動 spawn workers → finalizer 自動 `terminate()` → `wait(timeout=5)` → `kill()` 兜底
- Redis db 在 fixture setup 與 teardown 各 `FLUSHDB` 一次
- **理由**：避免測試間污染；finalizer 保證即使 assertion fail 也清理

## Risks / Trade-offs

- **Worker subprocess 啟動慢** → fixture session-scoped 重用 worker，每個測試只清 Redis state（不重啟 worker）
- **CI runner 資源限制（記憶體/檔案描述符）** → 限制 max_workers=3、CI 中標記 `@pytest.mark.multi_worker` 避免與其他重測試同時跑
- **Flaky 風險（job 排程順序非確定性）** → 用 barrier 同步，不對「誰先拿到」做斷言；只對「總執行次數」、「無重複副作用」、「無永久飢餓」做斷言
- **Worker stderr 噪音** → harness 收集 worker stdout/stderr 至 fixture 變數，失敗時印出供 debug
- **測試暴露生產 bug 怎麼辦** → 本變更**只新增測試**；若失敗顯示生產缺陷，於 tasks.md 註記 follow-up issue，不在本變更內修

## Migration Plan

1. 建 `tests/integration/_multi_worker_harness.py`（worker subprocess 管理、barrier、cleanup）
2. 建 `tests/integration/test_multi_worker_concurrency.py` 逐一覆蓋 5 個情境
3. 註冊 `multi_worker` marker 至 `pytest.ini`
4. 本地執行 `pytest -m multi_worker` 驗證
5. CI workflow 新增獨立 step（建議與既有 integration tests 分開 job）
6. 若任一測試失敗顯示真實併發 bug，開 follow-up issue（不阻塞本變更歸檔）

**Rollback**：移除 `tests/integration/test_multi_worker_concurrency.py` 與 harness、移除 marker、移除 CI step。無 production 影響。

## Open Questions

- CI runner 是否允許 spawn subprocess 並連接 Redis？需先確認 runner 權限
- worker subprocess 啟動失敗（如 port busy）如何 surface？harness 應在 fixture setup 階段健康檢查並 `pytest.skip`
- `lock TTL` 預設多少？需查 production 程式碼確認測試時的等待上限
