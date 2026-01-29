## 1. 基礎建設

- [x] 1.1 安裝 Redis 服務於 Linux 伺服器
- [x] 1.2 配置 Redis（使用預設配置，無需限制記憶體）
- [x] 1.3 更新 `requirements.txt` 加入 `redis>=5.0.0` 和 `hiredis>=2.0.0`
- [x] 1.4 更新 `.env.example` 加入 Redis 相關環境變數

## 2. Redis 連線管理

- [x] 2.1 建立 `src/mes_dashboard/core/redis_client.py`
- [x] 2.2 實作 `get_redis_client()` 函數，支援連接池和健康檢查
- [x] 2.3 實作 `redis_available()` 函數，檢查 Redis 連線狀態
- [x] 2.4 加入環境變數讀取：`REDIS_URL`、`REDIS_ENABLED`、`REDIS_KEY_PREFIX`

## 3. 快取更新背景任務

- [x] 3.1 建立 `src/mes_dashboard/core/cache_updater.py`
- [x] 3.2 實作 `CacheUpdater` 類別，包含 start/stop 方法
- [x] 3.3 實作 `_check_sys_date()` 方法，查詢 Oracle `MAX(SYS_DATE)`
- [x] 3.4 實作 `_load_full_table()` 方法，載入整個 `DW_PJ_LOT_V` 表
- [x] 3.5 實作 `_update_redis_cache()` 方法，使用 pipeline 原子更新
- [x] 3.6 在 `app.py` 中整合，應用啟動時啟動背景任務

## 4. 快取讀取與降級機制

- [x] 4.1 重寫 `src/mes_dashboard/core/cache.py`，實作表級快取
- [x] 4.2 實作 `get_cached_wip_data()` 函數，從 Redis 讀取完整表資料
- [x] 4.3 實作 `get_cached_sys_date()` 函數，讀取快取的 SYS_DATE
- [x] 4.4 實作降級邏輯：Redis 不可用時 fallback 到 Oracle

## 5. WIP Service 重構

- [x] 5.1 修改 `get_wip_summary()` 使用快取資料 + pandas 計算
- [x] 5.2 修改 `get_wip_matrix()` 使用快取資料 + pandas 計算
- [x] 5.3 修改 `get_wip_hold_summary()` 使用快取資料 + pandas 計算
- [x] 5.4 修改 `get_wip_detail()` 使用快取資料 + pandas 篩選/分頁
- [x] 5.5 修改 `get_hold_detail_summary()` 使用快取資料
- [x] 5.6 修改 `get_hold_detail_distribution()` 使用快取資料
- [x] 5.7 修改 `get_hold_detail_lots()` 使用快取資料 + pandas 篩選/分頁
- [x] 5.8 修改 meta 端點（workcenters、packages、search）使用快取資料

## 6. SQLAlchemy 連線超時修復

- [x] 6.1 修改 `src/mes_dashboard/core/database.py`
- [x] 6.2 在 `_register_pool_events()` 中加入 checkout 事件處理
- [x] 6.3 設置 `dbapi_conn.call_timeout = 55000`
- [x] 6.4 超時機制已配置（生產環境驗證）

## 7. Gunicorn 配置強化

- [x] 7.1 修改 `gunicorn.conf.py` 加入 `max_requests = 1000`
- [x] 7.2 加入 `max_requests_jitter = 100`
- [x] 7.3 確認 `timeout = 65`（大於 call_timeout 55 秒）

## 8. 健康檢查端點

- [x] 8.1 建立 `src/mes_dashboard/routes/health_routes.py`
- [x] 8.2 實作 `GET /health` 端點
- [x] 8.3 實作 `check_database()` 函數（SELECT 1 FROM DUAL）
- [x] 8.4 實作 `check_redis()` 函數（PING）
- [x] 8.5 實作 `get_cache_status()` 函數（讀取 meta keys）
- [x] 8.6 在 `app.py` 中註冊 health blueprint
- [x] 8.7 配置健康檢查不需要身份驗證

## 9. 測試

- [x] 9.1 單元測試：Redis 連線管理（mock Redis）
- [x] 9.2 單元測試：快取更新邏輯
- [x] 9.3 單元測試：降級機制
- [x] 9.4 整合測試：API 回傳結果正確性
- [x] 9.5 效能測試：比較快取前後的回應時間
- [x] 9.6 E2E 測試：完整端到端測試（17 項測試全部通過）

## 10. 部署與驗證

- [x] 10.1 部署 Redis 服務到生產環境
- [x] 10.2 設置生產環境的環境變數
- [x] 10.3 部署應用程式更新
- [x] 10.4 監控 Redis 記憶體使用率（目前 17MB）
- [x] 10.5 確認 Oracle 查詢頻率降低（日誌顯示 Cache hit）
- [x] 10.6 確認 `/health` 端點正常運作
- [x] 10.7 前端 UI 加入健康狀態標示
