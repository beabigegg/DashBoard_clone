## Context

Login session 的 orphan 問題（頻繁重啟導致 `logout_time IS NULL`）造成在線人數與使用時長統計失真。同時 portal-shell HealthStatus popup 只覆蓋 DB/Redis/快取，缺少記憶體、連線池、RQ Worker、背景服務等關鍵資訊。此變更同時修復 session 精確度並擴充系統狀態可觀測性。

## Goals / Non-Goals

**Goals:**
- 修正 orphan session 問題，讓 `duration_sec` 反映真實使用時間
- 在 portal-shell 頂欄顯示在線人數
- 擴充 HealthStatus popup 為四區分類，涵蓋核心服務/系統資源/快取/背景服務
- `/health` endpoint 補齊 SyncWorker、Anomaly Scheduler、在線人數
- Admin UsageTab 加在線趨勢圖

**Non-Goals:**
- 不做 WebSocket/SSE 即時推送
- 不暴露深層背景服務（scrap exclusion、query spool cleanup、metrics history collector）到 portal-shell
- 不做 DuckDB 前端狀態監控
- 不做 slow query 明細 list

## Decisions

### D1. Graceful shutdown 清理 orphan session

在 `_shutdown_runtime_resources()` 中，於 SyncWorker stop **之前**，呼叫 `LoginSessionStore.close_all_active_sessions()`，將所有 `logout_time IS NULL` 的 session 以 `last_active` 作為結束時間關閉。

- 替代方案：在 Gunicorn `worker_exit` hook 中處理
- 為何不選：`_shutdown_runtime_resources` 已經是統一的 shutdown 入口且透過 `atexit` 註冊，不需要額外的 Gunicorn hook

### D2. duration_sec 改用 last_active 計算

`close_session()` 的 duration 計算改為 `last_active - login_time`。如果 `last_active` 為 NULL（極少數情況），fallback 到 `now - login_time`。

- 替代方案：繼續用 `logout_time - login_time`
- 為何不選：logout_time 對 orphan 和開發重啟場景會嚴重偏大

### D3. SyncWorker 保底 orphan 清理

在 `SyncWorker._run()` 的每輪迴圈中加入 `_cleanup_orphan_sessions()` 步驟，掃描 `login_time < now - 8h AND logout_time IS NULL` 的 session，用 `last_active` 關閉。

- 替代方案：另起獨立 daemon thread
- 為何不選：SyncWorker 已有 10 分鐘週期且持有 `_login_store` 引用，搭便車最簡單

### D4. MySQL 歷史資料清理

新增一次性 migration：`TRUNCATE TABLE dashboard_login_sessions`。在 SyncWorker `_ensure_mysql_tables()` 中執行，透過一個 version flag 確保只跑一次。

- 替代方案：逐筆刪除失真資料
- 為何不選：所有歷史 duration 都可能失真，全清最乾淨

### D5. Heartbeat 夾帶在線人數（方案 C）

`PATCH /api/auth/heartbeat` 的 response 中新增 `online_count` 欄位。後端透過 `LoginSessionStore.get_active_count()` 查詢 `logout_time IS NULL AND last_active >= now - 30min`。

- 前端 `useAuth.js` 的 `startHeartbeat()` 解析 response 並更新一個 reactive ref
- portal-shell header 訂閱此 ref 顯示人數
- 替代方案：獨立 polling endpoint
- 為何不選：heartbeat 每 5 分鐘已有請求，零成本搭便車

### D6. HealthStatus popup 四區重構

將現有 popup 重新分為四區：

```
┌─ 核心服務 ──────────────────────┐
│ Oracle DB    🟢 Pool 35%        │
│ Redis        🟢 正常            │
│ Circuit Breaker  🟢 CLOSED      │
├─ 系統資源 ──────────────────────┤
│ 記憶體       🟢 62% (1.5/2.5GB) │
│ 在線人數     👤 12              │
├─ 快取 ──────────────────────────┤
│ WIP 快取     已啟用  同步 15:20  │
│ 設備主檔     已載入  1244 筆     │
│ 路由快取     redis  L1/L2 92/78 │
│ Workcenter   37 wc / 27 groups  │
├─ 背景服務 ──────────────────────┤
│ RQ Workers   🟢 2/2  Queue: 0   │
│ MySQL Sync   🟢 last: 15:20     │
│ Anomaly      🟢 64 anomalies    │
└─────────────────────────────────┘
```

資料來源不變，仍是 `/health` endpoint 回傳的 JSON，只是前端 popup 多讀幾個已有欄位 + 新增的 `sync_worker` / `anomaly_scheduler` / `online_count` 欄位。

- 替代方案：保持單層列表，只加新項目
- 為何不選：項目增多後難以掃讀，分區提高可讀性

### D7. `/health` endpoint 補齊

在 `/health` response 中新增三個頂層欄位：

```python
"sync_worker": {
    "running": True,
    "last_sync_at": "2026-03-26T15:20:00"
},
"anomaly_scheduler": {
    "running": True,
    "last_run": "2026-03-26T08:00:00",
    "anomaly_count": 64
},
"online_count": 12
```

SyncWorker 和 AnomalyScheduler 各需暴露一個 `get_status()` 類方法/模組函式，回傳上述結構。

### D8. Admin UsageTab 在線趨勢

在 `user_usage_kpi_service` 中新增 `online_trend` 欄位，從 `dashboard_metrics_snapshots` 的 `rq_workers_total` 附近取 — 或更簡單地，在每次 metrics snapshot 時額外記錄 `online_count`，讓 `performance-history` API 回傳此序列。

- 前端 UsageTab 用現有 `TrendChart` 元件渲染折線圖
- 替代方案：在 KPI API 中即時計算歷史在線
- 為何不選：login_sessions 表沒有時序快照，從 metrics_history 取更自然

## Data Flow

```
  Heartbeat (每 5 min)                    Health Check (每 30s)
  ┌──────┐  PATCH /auth/heartbeat  ┌──────────┐  GET /health  ┌──────────┐
  │ 前端 │ ──────────────────────▶ │ 後端     │ ◀──────────── │ 前端     │
  │      │ ◀── { online_count } ── │          │ ──────────▶   │ Health   │
  │useAuth│                        │ SQLite   │  full status  │ Status   │
  └──┬───┘                        └────┬─────┘               └──────────┘
     │                                  │
     │  online_count ref                │ SyncWorker (每 10 min)
     ▼                                  │ ├─ sync → MySQL
  ┌──────┐                             │ ├─ cleanup orphans
  │Header│ 👤 12                       │ └─ record online_count in metrics
  └──────┘                             ▼
                                 ┌──────────┐
                                 │  MySQL   │ ← Admin KPI API reads from here
                                 └──────────┘
```

## File Change Summary

| Area | File | Change |
|------|------|--------|
| Session Store | `core/login_session_store.py` | 新增 `close_all_active_sessions()`, `get_active_count()`; 修改 `close_session()` duration 計算 |
| Shutdown | `app.py` | 在 `_shutdown_runtime_resources` 加入 session cleanup |
| SyncWorker | `core/sync_worker.py` | 加入 `_cleanup_orphan_sessions()` 步驟; 新增 `get_sync_worker_status()`; MySQL 資料清理 migration |
| Anomaly | `services/anomaly_detection_scheduler.py` | 新增 `get_anomaly_scheduler_status()` |
| Auth Routes | `routes/user_auth_routes.py` | heartbeat response 加 `online_count` |
| Health | `routes/health_routes.py` | `/health` 補齊 sync_worker, anomaly_scheduler, online_count |
| Metrics | `core/metrics_history.py` | snapshot 加入 `online_count` 欄位 |
| KPI Service | `services/user_usage_kpi_service.py` | 回傳 `online_trend` 資料 |
| Frontend Auth | `portal-shell/composables/useAuth.js` | heartbeat response 解析 online_count |
| Frontend Health | `portal-shell/components/HealthStatus.vue` | 四區重構 + 新欄位 |
| Frontend Admin | `admin-dashboard/tabs/OverviewTab.vue` | 顯示 sync/anomaly 狀態 |
| Frontend Admin | `admin-dashboard/tabs/UsageTab.vue` | 在線趨勢圖 |
