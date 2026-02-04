## 1. 基礎設施模組

- [x] 1.1 建立 `core/response.py` - API 回應格式工具
  - 實作 `success_response(data, meta=None)` 函數
  - 實作 `error_response(code, message, details=None)` 函數
  - 定義標準錯誤代碼常數 (DB_CONNECTION_FAILED, DB_QUERY_TIMEOUT, SERVICE_UNAVAILABLE, VALIDATION_ERROR, UNAUTHORIZED, FORBIDDEN, NOT_FOUND, INTERNAL_ERROR)

- [x] 1.2 建立 `core/circuit_breaker.py` - 熔斷器模組
  - 實作 CircuitBreaker 類別，支援 CLOSED/OPEN/HALF_OPEN 狀態
  - 實作滑動視窗計數 (window_size=10)
  - 支援環境變數配置 (CIRCUIT_BREAKER_ENABLED, CIRCUIT_BREAKER_FAILURE_THRESHOLD 等)
  - 實作 `get_circuit_breaker_status()` 查詢狀態
  - 實作狀態轉換日誌記錄

- [x] 1.3 建立 `core/metrics.py` - 效能指標收集模組
  - 實作 QueryMetrics 類別，使用 deque(maxlen=1000)
  - 實作 P50/P95/P99 百分位數計算
  - 追蹤慢查詢數量 (> 1秒)
  - 支援 worker PID 識別

- [x] 1.4 擴展 `core/cache.py` - 本地快取 Fallback (部分完成)
  - [x] 實作 ProcessLevelCache 類別 (TTL-aware)
  - [x] 實作 WIP DataFrame 的 process-level 快取
  - [x] 實作 Resource Cache 的 process-level 快取
  - [x] 實作 Equipment Status Cache 的 process-level 快取
  - [ ] 實作通用 LRU cache 介面 (maxsize=500, ttl=60s)
  - [ ] 追蹤命中率統計 (hits, misses, hit_rate)
  - [ ] 支援環境變數 LOCAL_CACHE_ENABLED, LOCAL_CACHE_MAXSIZE

- [x] 1.5 建立 `core/log_store.py` - SQLite log store
  - 建立 logs 資料表（時間、等級、來源、訊息、request_id、user、ip）
  - 支援查詢參數：level, q, limit, since
  - 實作保留策略（預設 7 天或 100,000 筆）
  - 支援環境變數 LOG_SQLITE_PATH, LOG_SQLITE_RETENTION_DAYS, LOG_SQLITE_MAX_ROWS

- [x] 1.6 整合應用程式 logging handler
  - 於 `app.py` 註冊 SQLite log handler
  - 保留原有檔案/STDERR log

- [x] 1.7 撰寫基礎設施模組單元測試
  - Circuit Breaker 狀態轉換測試
  - Metrics 百分位數計算測試
  - Local Cache LRU 與 TTL 測試
  - SQLite log store 讀寫與保留策略測試

## 2. 資料庫層整合

- [x] 2.1 整合熔斷器到 `core/database.py`
  - 在 `read_sql_df()` 加入熔斷器檢查
  - OPEN 狀態時立即回傳錯誤
  - 記錄成功/失敗到熔斷器
  - 預設停用，透過 CIRCUIT_BREAKER_ENABLED=true 啟用

- [x] 2.2 整合效能指標到 `core/database.py`
  - 記錄每次查詢延遲
  - 記錄慢查詢 (> 1秒) 到 metrics

- [x] 2.3 整合本地快取 Fallback 到快取層 (已由 1.4 ProcessLevelCache 實現)
  - Redis 失敗時查詢本地 LRU Cache
  - Oracle 查詢結果回填到 Redis 和本地快取

## 3. API 回應格式遷移

- [x] 3.1 在 `app.py` 註冊全域錯誤處理器
  - @app.errorhandler(401) - UNAUTHORIZED
  - @app.errorhandler(403) - FORBIDDEN
  - @app.errorhandler(404) - NOT_FOUND
  - @app.errorhandler(500) - INTERNAL_ERROR
  - @app.errorhandler(Exception) - 未捕獲例外

- [x] 3.2 更新認證中介層回應格式
  - `@app.before_request` 的拒絕回應改用統一格式

- [x] 3.3 逐步遷移各 Blueprint 使用新回應格式
  - 新 API 直接使用 success_response/error_response
  - 現有 API 保持向下相容

## 4. 健康檢查端點

- [x] 4.1 實作 `/health/deep` 深度健康檢查端點
  - 需要 @admin_required 認證
  - 包含資料庫延遲與連線池狀態
  - 包含 Redis 延遲 (如啟用)
  - 包含熔斷器狀態
  - 包含快取新鮮度與命中率
  - 包含效能指標摘要 (P50/P95/P99)

- [x] 4.2 實作延遲警告閾值
  - 資料庫延遲 > 100ms 標記為 "slow"
  - 快取更新 > 2 分鐘標記為 "stale"
  - 熔斷器 OPEN 時整體狀態為 "degraded"

## 5. 效能報表頁面

- [x] 5.1 建立 `GET /admin/performance` 頁面路由
  - 需要管理員權限
  - 使用現有 admin template 風格

- [x] 5.2 實作 `GET /admin/api/system-status` API
  - 回傳 database, redis, circuit_breaker, cache, worker_pid

- [x] 5.3 實作 `GET /admin/api/metrics` API
  - 回傳 P50/P95/P99, slow_count, slow_rate, worker_pid

- [x] 5.4 建立效能報表前端頁面
  - 系統狀態卡片 (Database, Redis, Circuit Breaker, Worker)
  - 延遲百分位數顯示
  - 慢查詢統計
  - 延遲分布圖表 (Chart.js)
  - 快取命中率顯示
  - 手動/自動重新整理 (30秒間隔)

- [x] 5.5 實作 `GET /admin/api/logs` API
  - 從 SQLite log store 讀取
  - 支援 level/q/limit/since 查詢參數

- [x] 5.6 效能報表頁面加入 Log 檢視區塊
  - 顯示最近 200 筆
  - 支援等級篩選與關鍵字搜尋
  - 與自動重新整理同步更新

## 6. Worker 重啟控制

- [x] 6.1 建立 `scripts/worker_watchdog.py` 腳本
  - 每 5 秒檢查 `/tmp/mes_dashboard_restart.flag`
  - 偵測到時發送 SIGHUP 給 Gunicorn master
  - 刪除 flag 檔案
  - 記錄重啟事件到日誌

- [x] 6.2 實作 `POST /admin/api/worker/restart` API
  - 需要 @admin_required
  - 寫入重啟標記檔案
  - 60 秒冷卻時間 (429 Too Many Requests)
  - 記錄操作者、時間、IP 到日誌

- [x] 6.3 實作 `GET /admin/api/worker/status` API
  - 回傳 cooldown_remaining, last_restart, last_restart_by
  - 回傳當前 worker 啟動時間

- [x] 6.4 效能報表頁面加入 Worker 控制區塊
  - 重啟按鈕 + 確認對話框
  - 冷卻狀態顯示
  - 最後重啟資訊
  - 重啟中狀態輪詢

## 7. 部署與測試

- [x] 7.1 建立 systemd service 檔案
  - `mes-dashboard-watchdog.service` 監控腳本

- [x] 7.2 撰寫整合測試
  - 熔斷器觸發與恢復測試
  - API 回應格式驗證測試
  - 健康檢查端點測試
  - 管理員 log API 測試
  - Worker 控制 API 測試

- [x] 7.3 更新部署文件
  - 新增環境變數說明
  - Watchdog 服務配置
  - Rollback 步驟
