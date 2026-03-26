## 1. Session Lifecycle 修復

- [x] 1.1 在 `core/login_session_store.py` 新增 `get_active_count()` 方法（`COUNT WHERE logout IS NULL AND last_active >= now-30min`）
- [x] 1.2 在 `core/login_session_store.py` 新增 `close_all_active_sessions()` 方法（用 `last_active` 關閉所有 `logout IS NULL` 的 session）
- [x] 1.3 修改 `close_session()` 的 duration 計算，改用 `last_active - login_time`（fallback `now - login_time`）
- [x] 1.4 在 `app.py` 的 `_shutdown_runtime_resources()` 中，於 SyncWorker stop 之前呼叫 `close_all_active_sessions()`
- [x] 1.5 在 `core/sync_worker.py` 的 `_run()` 迴圈加入 `_cleanup_orphan_sessions()` 步驟（掃描 > 8h orphan）
- [x] 1.6 在 `core/sync_worker.py` 加入一次性 MySQL migration：`TRUNCATE TABLE dashboard_login_sessions`（version flag 控制）

## 2. 在線人數（Online Presence）

- [x] 2.1 修改 `routes/user_auth_routes.py` heartbeat endpoint，response 加入 `online_count`（呼叫 `get_active_count()`）
- [x] 2.2 修改 `portal-shell/composables/useAuth.js`，heartbeat callback 解析 `online_count` 並暴露為 reactive ref
- [x] 2.3 在 `portal-shell/App.vue` header 中加入在線人數顯示（user icon + count），從 `useAuth` 取值
- [x] 2.4 在 `portal-shell/style.css` 加入在線人數的樣式

## 3. 系統狀態增強 — 後端

- [x] 3.1 在 `core/sync_worker.py` 新增 `get_sync_worker_status()` 函式，回傳 `{ running, last_sync_at }`
- [x] 3.2 在 `services/anomaly_detection_scheduler.py` 新增 `get_anomaly_scheduler_status()` 函式，回傳 `{ running, last_run, anomaly_count }`
- [x] 3.3 在 `routes/health_routes.py` 的 `/health` response 中加入 `sync_worker`、`anomaly_scheduler`、`online_count` 欄位

## 4. 系統狀態增強 — 前端

- [x] 4.1 重構 `portal-shell/components/HealthStatus.vue` popup 為四區佈局（核心服務/系統資源/快取/背景服務）
- [x] 4.2 在核心服務區加入 DB pool 飽和度、Circuit Breaker 狀態
- [x] 4.3 在系統資源區加入記憶體使用情況、在線人數
- [x] 4.4 在快取區加入 Workcenter mapping 資訊
- [x] 4.5 在背景服務區加入 RQ Workers、SyncWorker、Anomaly Scheduler 狀態
- [x] 4.6 在 `portal-shell/style.css` 加入四區 popup 的樣式

## 5. Admin Dashboard 增強

- [x] 5.1 在 `core/metrics_history.py` 的 snapshot 中加入 `online_count` 欄位
- [x] 5.2 在 `core/sync_worker.py` 的 `_ensure_mysql_tables()` 中，為 `dashboard_metrics_snapshots` 表加入 `online_count` 欄位（ALTER TABLE IF NOT EXISTS）
- [x] 5.3 在 `admin-dashboard/tabs/OverviewTab.vue` 加入 SyncWorker 和 Anomaly Scheduler 狀態顯示
- [x] 5.4 在 `admin-dashboard/tabs/UsageTab.vue` 加入在線趨勢圖（使用 TrendChart 元件）

## 6. 驗證

- [ ] 6.1 手動驗證：啟動伺服器 → 登入 → 重啟伺服器 → 確認 orphan session 被正確關閉、duration 合理
- [ ] 6.2 手動驗證：確認 heartbeat response 包含 online_count、header 顯示正確
- [ ] 6.3 手動驗證：HealthStatus popup 四區顯示正確，所有欄位有值
- [ ] 6.4 手動驗證：Admin OverviewTab 顯示 SyncWorker/Anomaly 狀態，UsageTab 顯示在線趨勢
- [ ] 6.5 執行 `pytest tests/ -v` 確認無回歸
