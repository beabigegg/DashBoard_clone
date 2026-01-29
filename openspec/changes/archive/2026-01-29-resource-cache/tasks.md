## 1. 新增 Resource Cache 模組

- [x] 1.1 建立 `src/mes_dashboard/services/resource_cache.py` 模組骨架
- [x] 1.2 實作 `_load_from_oracle()` - 從 Oracle 載入全表資料（套用全域篩選）
- [x] 1.3 實作 `_sync_to_redis()` - 使用 pipeline 原子寫入 Redis
- [x] 1.4 實作 `_get_version_from_oracle()` - 查詢 `MAX(LASTCHANGEDATE)`
- [x] 1.5 實作 `_get_version_from_redis()` - 讀取 Redis 版本
- [x] 1.6 實作 `refresh_cache(force)` - 版本比對與同步邏輯
- [x] 1.7 實作 `init_cache()` - 初始化載入

## 2. 實作查詢 API

- [x] 2.1 實作 `get_all_resources()` - 取得所有快取資料
- [x] 2.2 實作 `get_resource_by_id()` - 依 ID 取得單筆
- [x] 2.3 實作 `get_resources_by_ids()` - 批次取得
- [x] 2.4 實作 `get_resources_by_filter()` - Python 端篩選

## 3. 實作篩選器選項 API

- [x] 3.1 實作 `get_distinct_values(column)` - 取得欄位唯一值
- [x] 3.2 實作 `get_resource_families()` - 型號清單便捷方法
- [x] 3.3 實作 `get_workcenters()` - 站點清單便捷方法
- [x] 3.4 實作 `get_departments()` - 部門清單便捷方法

## 4. 實作快取狀態 API

- [x] 4.1 實作 `get_cache_status()` - 回傳快取狀態資訊
- [x] 4.2 實作 Oracle fallback 邏輯（Redis 不可用時）

## 5. 整合背景同步任務

- [x] 5.1 修改 `cache_updater.py` 加入 resource 同步間隔配置
- [x] 5.2 實作 `_check_resource_update()` 方法
- [x] 5.3 在主迴圈加入 resource 同步檢查
- [x] 5.4 啟動時觸發初始同步

## 6. 環境變數配置

- [x] 6.1 新增 `RESOURCE_CACHE_ENABLED` 環境變數支援
- [x] 6.2 新增 `RESOURCE_SYNC_INTERVAL` 環境變數支援
- [x] 6.3 更新 `.env.example` 範例

## 7. 整合設備歷史績效

- [x] 7.1 修改 `resource_history_service.get_filter_options()` 使用 resource_cache
- [x] 7.2 驗證 `/api/resource/history/options` 端點正常運作 (18 workcenter_groups, 152 families)
- [x] 7.3 驗證前端 `familiesDropdown` 型號篩選器 (用戶確認可用)

## 8. 整合機台狀態報表

- [x] 8.1 修改 `resource_service.query_resource_filter_options()` 使用 resource_cache
- [x] 8.2 驗證 `/resource/filter_options` 端點正常運作 (18 workcenters, 152 families, 6 statuses)
- [x] 8.3 驗證前端所有篩選器（站點、型號、部門）(用戶確認可用)

## 9. 清理舊程式碼

- [x] 9.1 移除 `filter_cache.get_resource_families()` 函數
- [x] 9.2 移除 `filter_cache._load_resource_families()` 函數
- [x] 9.3 更新相關 import 語句

## 10. Health Check 整合

- [x] 10.1 修改 `/health` 端點加入 `resource_cache` 狀態
- [x] 10.2 快取未載入時加入 warning 訊息
- [x] 10.3 更新前端 health popup 顯示 resource cache 狀態（可選）

## 11. 測試

- [x] 11.1 新增 `tests/test_resource_cache.py` 單元測試 (28 tests passed)
- [x] 11.2 測試 Redis 同步邏輯
- [x] 11.3 測試查詢 API
- [x] 11.4 測試 fallback 機制
- [x] 11.5 測試環境變數配置
- [x] 11.6 執行整合測試驗證篩選器功能 (15 tests passed)
- [x] 11.7 新增 `tests/e2e/test_resource_cache_e2e.py` E2E 測試 (待服務重啟後驗證)
