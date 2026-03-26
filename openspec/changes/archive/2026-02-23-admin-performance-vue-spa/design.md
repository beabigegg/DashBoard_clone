## Context

現有 `/admin/performance` 是 Jinja2 server-rendered 頁面（vanilla JS + Chart.js），是唯一未遷移至 Vue 3 SPA 的前端頁面。後端已具備豐富的監控數據（連線池 `get_pool_status()`、Redis client、LayeredCache `.telemetry()`），但前端僅展示 4 張 status cards + query performance + worker control + logs，缺少 Redis 詳情、ProcessLevelCache 統計、連線池飽和度等關鍵面板。

## Goals / Non-Goals

**Goals:**
- 將 admin/performance 頁面從 Jinja2 切換為 Vue 3 SPA，與所有報表頁面架構一致
- 新增完整的系統監控面板：Redis 快取詳情、ProcessLevelCache 統計、連線池飽和度、直連 Oracle 追蹤
- 提供可複用的 gauge/stat card 組件，便於未來擴展監控項目
- 保留所有既有功能（status cards、query performance、worker control、system logs）

**Non-Goals:**
- 不新增告警/通知機制（未來可擴展）
- 不引入 WebSocket 即時推送（維持 30 秒輪詢）
- 不修改既有 API response format（`system-status`、`metrics`、`logs` 保持不變）
- 不新增使用者權限控制（沿用既有 admin 認證）

## Decisions

### 1. Vue 3 SPA + ECharts 取代 Jinja2 + Chart.js

**選擇**: 全面重建為 Vue 3 SPA，使用 ECharts 繪製圖表

**理由**: 所有報表頁面已完成 Vue SPA 遷移，admin/performance 是最後一個 Jinja2 頁面。統一架構可複用 `apiGet`、`useAutoRefresh` 等共用基礎設施，減少維護成本。ECharts 已是專案標準圖表庫（query-tool、reject-history 等均使用）。

**替代方案**: 保留 Jinja2 僅加 API — 但會持續累積技術債，且無法複用 Vue 生態。

### 2. 單一 performance-detail API 聚合所有新增監控數據

**選擇**: 新增 `GET /admin/api/performance-detail` 一個 endpoint，回傳 `redis`、`process_caches`、`route_cache`、`db_pool`、`direct_connections` 五個 section。

**理由**: 減少前端並發請求數（已有 5 個 API，加 1 個共 6 個），後端可在同一 request 中順序收集各子系統狀態，避免多次 round-trip。

**替代方案**: 每個監控維度獨立 endpoint — 更 RESTful 但增加前端複雜度和網路開銷。

### 3. ProcessLevelCache 全域 registry 模式

**選擇**: 在 `core/cache.py` 新增 `_PROCESS_CACHE_REGISTRY` dict + `register_process_cache()` 函式，各服務在模組載入時自行註冊。

**理由**: 避免 admin_routes 硬編碼各快取實例的 import 路徑，新增快取時只需在該服務中加一行 `register_process_cache()` 即可自動出現在監控面板。

**替代方案**: admin_routes 直接 import 各快取實例 — 耦合度高，新增快取需改兩處。

### 4. Redis namespace 監控使用 SCAN 而非 KEYS

**選擇**: 使用 `SCAN` 搭配 `MATCH` pattern 掃描各 namespace 的 key 數量。

**理由**: `KEYS *` 在生產環境會阻塞 Redis，`SCAN` 為非阻塞迭代器，安全性更高。

### 5. 直連 Oracle 使用 thread-safe atomic counter

**選擇**: 在 `database.py` 使用 `threading.Lock` 保護的全域計數器，在 `get_db_connection()` 和 `read_sql_df_slow()` 建立連線後 increment。

**理由**: 追蹤連線池外的直接連線使用量，幫助判斷是否需要調整池大小。計數器為 monotonic（只增不減），記錄的是自 worker 啟動以來的總數。

### 6. 前端組件複用 GaugeBar / StatCard / StatusDot

**選擇**: 新增 3 個小型可複用組件放在 `admin-performance/components/` 下。

**理由**: Redis 記憶體、連線池飽和度、ProcessLevelCache 使用率等多處需要 gauge 視覺化；status cards 跨面板重複。組件化可統一視覺風格並減少重複 template。

### 7. SQLite 持久化 metrics history store

**選擇**: 新增 `core/metrics_history.py`，使用 SQLite 儲存 metrics snapshots（仿 `core/log_store.py` 的 `LogStore` 模式），搭配 daemon thread 每 30 秒採集一次。

**理由**: in-memory deque 在 worker 重啟或 gunicorn prefork 下無法跨 worker 共享且不保留歷史。SQLite 提供跨 worker 讀取、重啟持久化、可配置保留天數（預設 3 天 / 50000 rows），且不需額外 infra。

**替代方案**:
- in-memory deque — 簡單但 worker 獨立、重啟即失
- Redis TSDB — 需額外模組且增加 Redis 負擔
- PostgreSQL — 太重，且此數據不需 ACID

**Schema**: `metrics_snapshots` table 含 timestamp、worker PID、pool/redis/route_cache/latency 各欄位，`idx_metrics_ts` 索引加速時間查詢。

**背景採集**: `MetricsHistoryCollector` daemon thread，間隔可透過 `METRICS_HISTORY_INTERVAL` 環境變數配置。在 `app.py` lifecycle 中 start/stop。

## Risks / Trade-offs

- **Redis SCAN 效能**: 大量 key 時 SCAN 可能較慢 → 設定 `COUNT 100` 限制每次迭代量，且 30 秒才掃一次，可接受
- **ProcessLevelCache registry 依賴模組載入順序**: 服務未 import 時不會註冊 → 在 app factory 或 gunicorn post_fork 確保所有服務模組已載入
- **直連計數器跨 worker 不共享**: gunicorn prefork 模式下每個 worker 有獨立計數 → API 回傳當前 worker PID 供辨識，可透過 `/admin/api/system-status` 的 worker info 交叉比對
- **舊 Jinja2 模板保留但不維護**: 切換後舊模板不再更新 → 透過 `routeContracts.js` 的 `rollbackStrategy: 'fallback_to_legacy_route'` 保留回退能力

## Migration Plan

1. 後端先行：加 `stats()`、registry、直連計數器、新 API（不影響既有功能）
2. 前端建構：新建 `admin-performance/` Vue SPA，Vite 註冊 entry
3. 路由切換：`admin_routes.py` 改為 `send_from_directory`，`routeContracts.js` 改 `renderMode: 'native'`
4. 驗證後部署：確認所有面板正確顯示後上線
5. 回退方案：`routeContracts.js` 改回 `renderMode: 'external'`，`admin_routes.py` 改回 `render_template`
