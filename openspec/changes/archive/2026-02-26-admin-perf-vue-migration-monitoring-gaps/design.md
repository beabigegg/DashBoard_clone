## Context

2026-02-25 的 server crash 暴露出 pool 隔離架構變更後的監控盲區。event_fetcher 和 lineage_engine 已遷移到 `read_sql_df_slow`（獨立連線 + semaphore），但 metrics_history 快照只記錄 pool 相關指標，slow query 並行數、排隊數、Worker RSS 完全無歷史紀錄。

同時 `/admin/performance` 仍保留 1249 行 Jinja template 作為 Vue SPA fallback，但 SPA 已是唯一使用的版本（build artifact 存在於 `static/dist/admin-performance.html`），兩套 UI 增加維護成本且 Jinja 版功能遠不及 SPA。

`logs/archive/` 目錄累積 rotated log 檔案無自動清理，是唯一會無限增長的儲存。

## Goals / Non-Goals

**Goals:**
- 移除 Jinja fallback，統一為 Vue SPA 單一架構
- 讓 slow query 並行數、排隊數、Worker RSS 成為可觀測的歷史趨勢指標
- 讓 P50/P95/P99 反映所有查詢路徑（pool + slow path）
- 解決 archive log 無限增長問題

**Non-Goals:**
- 不修改 `/admin/pages`（仍為 Jinja template）
- 不新增 async job queue 面板（P1，後續 change 處理）
- 不新增 event cache hit/miss 計數器（P2）
- 不增加即時告警或 webhook 通知機制

## Decisions

### D1：SQLite schema migration 策略

**選擇**：啟動時執行 `ALTER TABLE ADD COLUMN IF NOT EXISTS`（容錯 "duplicate column" error）

**替代方案**：version table + migration script → 過度工程，SQLite 只有 3 天保留，加欄是向後相容的

**理由**：新欄位 nullable，舊 row 自動為 NULL，不影響既有查詢。MetricsHistoryStore.initialize() 已在啟動時執行 CREATE TABLE IF NOT EXISTS，加入 ALTER TABLE 語句自然整合。

### D2：RSS 記憶體取得方式

**選擇**：`resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024`（Python stdlib，Linux 上單位為 KB）

**替代方案 A**：讀取 `/proc/self/status` VmRSS → 平台相依，解析 overhead
**替代方案 B**：`psutil.Process().memory_info().rss` → 需新增外部依賴

**理由**：`resource` 模組為 Python 標準庫，無需額外依賴。`ru_maxrss` 在 Linux 上返回 KB，乘以 1024 轉為 bytes。

### D3：Semaphore 排隊計數器實作

**選擇**：在 `read_sql_df_slow()` 的 semaphore.acquire() 前後遞增/遞減 `_SLOW_QUERY_WAITING` atomic counter

**流程**：
```
_SLOW_QUERY_WAITING += 1
acquired = semaphore.acquire(timeout=60)
_SLOW_QUERY_WAITING -= 1
if not acquired: raise RuntimeError
_SLOW_QUERY_ACTIVE += 1
... execute query ...
_SLOW_QUERY_ACTIVE -= 1
```

**理由**：與既有 `_SLOW_QUERY_ACTIVE` 模式一致，使用 threading.Lock 保護。

### D4：Archive log cleanup 整合位置

**選擇**：整合到 `MetricsHistoryCollector._run()` 的 cleanup cycle（每 ~100 intervals ≈ 50 分鐘）

**替代方案**：獨立 cron job → 需額外 crontab 配置，不自包含

**理由**：已有 daemon thread 定期 cleanup SQLite，加入 archive cleanup 邏輯一致且自包含。

### D5：移除 Jinja fallback 的安全性

**選擇**：直接移除 fallback，admin_routes.py 改為只 `send_from_directory(dist_dir, "admin-performance.html")`

**理由**：
- Vue SPA build artifact 已存在（`static/dist/admin-performance.html`，2026-02-26 更新）
- `frontend/package.json` build script 已包含 admin-performance entry
- CI/deploy 流程必包含 `npx vite build`
- 若 build 失敗，`/health/frontend-shell` 已有 asset readiness 檢查可偵測

## Risks / Trade-offs

- **[Risk] Build 失敗時 /admin/performance 返回 404** → 既有 `/health/frontend-shell` 檢查 + deploy script 驗證。移除 fallback 反而讓問題更早暴露。
- **[Risk] ALTER TABLE 在 SQLite 大表上可能慢** → metrics_history 最多 50K rows，ALTER TABLE 即時完成。
- **[Trade-off] `ru_maxrss` 是 peak RSS，非 current RSS** → 在 Linux 上 `ru_maxrss` 是 process lifetime 的 max RSS。改用 `/proc/self/status` 的 VmRSS 可取得 current，但需 file I/O。鑑於每 30 秒收集一次且 max RSS 更能反映記憶體壓力，接受此 trade-off。若日後需要 current RSS，可改讀 `/proc/self/status`。
