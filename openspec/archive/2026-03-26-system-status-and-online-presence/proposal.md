# Proposal: System Status Enhancement & Online Presence

## Problem

### 1. Session Duration 失真
開發期間頻繁重啟服務時，login session 變成 orphan（`logout_time IS NULL`），導致：
- **在線人數判斷失真** — orphan session 在 30 分鐘後才會消失，但 `duration_sec` 永遠不會被寫入
- **使用時長失真** — orphan session 被清理時，`duration_sec = 清理時間 - login_time`，包含了停機時間
- 伺服器重啟後沒有任何 cleanup 機制

### 2. Portal-Shell 頂欄資訊不足
現有 HealthStatus popup 只顯示 DB/Redis/快取狀態，缺少：
- 在線人數
- 系統記憶體
- DB 連線池飽和度
- Circuit Breaker 狀態
- RQ Worker 狀態
- 背景服務（SyncWorker、Anomaly Scheduler）

### 3. Admin 後台缺口
- 在線人數趨勢圖不存在
- SyncWorker、Anomaly Scheduler 狀態沒有暴露在任何 UI

## Solution

### Part A: Session 修復 + 在線人數

1. **Graceful shutdown hook** — 在 Gunicorn `worker_exit` / Flask teardown 時，掃描所有 `logout_time IS NULL` 的 session，用 `last_active` 作為 `logout_time` 關閉
2. **duration_sec 改用 last_active** — `close_session()` 和 orphan 清理改為 `duration = last_active - login_time`（而非 `now - login_time`），更接近真實使用時間
3. **SyncWorker 搭便車清理** — 每 10 分鐘掃描 `> 8h && logout IS NULL` 的 orphan session，用 `last_active` 關閉，作為保底機制
4. **MySQL 歷史資料清理** — 刪除 `dashboard_login_sessions` 表中的舊資料（或 DROP + 重建），避免失真數據污染統計
5. **Heartbeat 夾帶在線人數** — `PATCH /api/auth/heartbeat` 的 response 中加入 `online_count`
6. **Portal-shell header 顯示在線人數** — 在頂欄 HealthStatus 旁邊或內部顯示 `👤 N`

### Part B: 系統狀態增強

1. **HealthStatus popup 重構** — 分類為「核心服務 / 系統資源 / 快取 / 背景服務」四區
2. **`/health` endpoint 補齊** — 新增以下欄位：
   - `sync_worker`: `{ running, last_sync_at }`
   - `anomaly_scheduler`: `{ running, last_run, anomaly_count }`
   - `online_count`: active session count
3. **Admin OverviewTab 補齊** — 顯示 SyncWorker 和 Anomaly Scheduler 狀態
4. **Admin UsageTab 加在線趨勢** — 在線人數隨時間的變化圖表

## Scope

### In Scope
- Login session orphan 修復（shutdown hook + SyncWorker 保底 + duration 計算修正）
- MySQL `dashboard_login_sessions` 資料清理
- Heartbeat response 夾帶 online_count
- Portal-shell header 在線人數顯示
- HealthStatus popup 擴充（memory, pool, circuit breaker, RQ, sync, anomaly）
- `/health` endpoint 補齊背景服務狀態
- Admin overview 補齊背景服務狀態
- Admin usage 加在線趨勢圖

### Out of Scope
- WebSocket / SSE 即時推送（polling 足夠）
- 深層背景服務狀態（scrap exclusion cache, query spool cleanup, metrics history collector — 只在 `/health/deep` 裡）
- DuckDB 前端狀態監控
- Slow query 明細 list（另開 change）

## Risk

| Risk | Mitigation |
|------|-----------|
| MySQL 資料清除影響報表 | duration 本來就失真，清除後重新累積更準確 |
| Shutdown hook 沒跑到（SIGKILL） | SyncWorker 保底清理每 10 分鐘跑一次 |
| HealthStatus popup 太多項目 | 分四區、預設摺疊背景服務區 |
| Heartbeat 查詢 online_count 增加 SQLite 壓力 | 簡單 COUNT + 已有 index，微秒級 |
