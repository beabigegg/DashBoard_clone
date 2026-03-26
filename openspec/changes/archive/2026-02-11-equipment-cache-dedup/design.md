## Context

`GUNICORN_WORKERS=4` 啟動 4 個 worker process，每個 worker 在 `init_realtime_equipment_cache()` 中各啟動一個 equipment sync daemon thread。現有分散式鎖（`try_acquire_lock`）只做序列化——worker A 釋放鎖後，worker B 取得鎖仍會查 Oracle，即使 worker A 剛寫入完全相同的資料。

現行 `_sync_worker()` 迴圈為 `refresh → wait(interval)`，首次進入即立刻 `refresh()`，與 init 的 `refresh_equipment_status_cache()` 形成 double-call。

**唯一修改檔案**：`src/mes_dashboard/services/realtime_equipment_cache.py`

## Goals / Non-Goals

**Goals:**
- 每個 5 分鐘同步週期只產生 1 次 Oracle 查詢（目前 4 次）
- 消除 init + sync thread 的 double-call
- 保留 `force=True` 繞過去重的能力

**Non-Goals:**
- 改變快取對外 API 行為或資料格式
- 改變 process-level cache（L1）的 TTL 或容量策略
- 單一 worker 架構（仍維持多 worker 架構）
- 更改分散式鎖本身的實作

## Decisions

### Decision 1: Freshness gate（取得鎖後檢查 Redis timestamp）

**方案 A（選用）**：取得分散式鎖後，讀取 Redis `equipment_status:meta:updated`。若 age < `_SYNC_INTERVAL // 2`，判定為 fresh，釋放鎖並跳過。

**方案 B（捨棄）**：取得鎖前先檢查 timestamp。問題：TOCTOU——檢查後鎖被另一個 worker 拿走並完成更新，本 worker 不知情。

**方案 C（捨棄）**：用 Redis SETNX 做 "sync epoch" marker 取代 timestamp 比較。增加額外 key 管理複雜度，沒有實際優勢。

**理由**：方案 A 最簡單，取得鎖後再檢查保證無 TOCTOU。threshold 設為 `interval / 2` 提供安全邊界——即使時鐘微漂移或 refresh 執行時間較長，也不會誤判。

### Decision 2: Wait-first sync worker loop

現行：`while not stop: refresh(); wait(interval)` → sync thread 啟動即 refresh（double-call）

改為：`while not _STOP_EVENT.wait(timeout=interval): refresh()` → sync thread 先等 interval 再首次 refresh

**理由**：`init_realtime_equipment_cache()` 已做首次同步，sync thread 不需要重複。`_STOP_EVENT.wait(timeout)` 返回 False 表示 timeout（繼續迴圈），返回 True 表示 stop signal（跳出）——語意清晰且是 Python threading 慣用模式。

### Decision 3: 模組級 `_SYNC_INTERVAL` 變數

`refresh_equipment_status_cache()` 需要知道 sync interval 來計算 freshness threshold。由 `init_realtime_equipment_cache()` 設定模組級變數 `_SYNC_INTERVAL`，default 300。

**理由**：避免在 refresh 函數中重新讀取 Flask config（refresh 可能在 app context 外被呼叫）。模組級變數是此 codebase 已有的慣例（如 `_STOP_EVENT`、`_SYNC_THREAD`）。

## Risks / Trade-offs

| 風險 | 緩解 |
|------|------|
| Freshness gate 過於激進導致整個週期無 worker 更新 | Threshold 為 `interval / 2`（150s），遠小於完整 interval（300s）。只要 1 個 worker 成功更新，其餘 worker 看到 age < 150s 就會跳過。若連 1 個 worker 都沒成功，150s 後下一個取得鎖的 worker 會正常更新。 |
| `_SYNC_INTERVAL` 在 init 前被 refresh 呼叫 | Default 值 300 確保安全。只有透過 init 才會啟動 sync thread，所以正常流程下 init 一定先於週期性 refresh。 |
| Wait-first loop 延遲首次週期性 refresh 5 分鐘 | 這是期望行為——init 已完成首次同步，sync thread 等 5 分鐘後才需要下一次。 |
