## 1. Configuration & Constants

- [x] 1.1 新增環境變數定義至 `config/settings.py`
  - `REALTIME_EQUIPMENT_CACHE_ENABLED` (default: true)
  - `EQUIPMENT_STATUS_SYNC_INTERVAL` (default: 300)
  - `WORKCENTER_MAPPING_SYNC_INTERVAL` (default: 86400)
- [x] 1.2 新增 Redis key 前綴常數至 `config/constants.py`
  - `EQUIPMENT_STATUS_DATA_KEY`
  - `EQUIPMENT_STATUS_INDEX_KEY`
  - `EQUIPMENT_STATUS_META_UPDATED_KEY`
  - `EQUIPMENT_STATUS_META_COUNT_KEY`
- [x] 1.3 新增 STATUS_CATEGORY_MAP 狀態分類對照表至 `config/constants.py`

## 2. Realtime Equipment Cache - Core

- [x] 2.1 建立 `services/realtime_equipment_cache.py` 模組骨架
- [x] 2.2 實作 `_load_equipment_status_from_oracle()` - 查詢 DW_MES_EQUIPMENTSTATUS_WIP_V
- [x] 2.3 實作 `_aggregate_by_resourceid()` - 依 RESOURCEID 聚合資料
  - 狀態欄位取任一筆
  - LOT_COUNT = COUNT(*)
  - TOTAL_TRACKIN_QTY = SUM(LOTTRACKINQTY_PCS)
  - LATEST_TRACKIN_TIME = MAX(LOTTRACKINTIME)
- [x] 2.4 實作 `_classify_status()` - 狀態分類邏輯
- [x] 2.5 實作 `_save_to_redis()` - 使用 pipeline 原子寫入 Redis

## 3. Realtime Equipment Cache - Query API

- [x] 3.1 實作 `get_all_equipment_status()` - 回傳全部快取資料
- [x] 3.2 實作 `get_equipment_status_by_id(resource_id)` - 單筆查詢
- [x] 3.3 實作 `get_equipment_status_by_ids(resource_ids)` - 批次查詢
- [x] 3.4 實作 `get_equipment_status_cache_status()` - 快取狀態查詢

## 4. Realtime Equipment Cache - Background Sync

- [x] 4.1 實作 `refresh_equipment_status_cache(force=False)` - 同步主函數
- [x] 4.2 實作 `_start_equipment_status_sync_worker()` - 背景 worker 啟動
- [x] 4.3 實作 `init_realtime_equipment_cache()` - 初始化函數（供 app 啟動呼叫）
- [x] 4.4 整合至 `app.py` - 應用程式啟動時初始化快取

## 5. Workcenter Mapping Cache

- [x] 5.1 擴充 `services/filter_cache.py` - 新增 workcenter mapping 相關變數
- [x] 5.2 實作 `_load_workcenter_mapping_from_spec()` - 查詢 DW_MES_SPEC_WORKCENTER_V
- [x] 5.3 實作 `get_workcenter_group(workcenter_name)` - 查詢工站分組
- [x] 5.4 實作 `get_workcenter_short(workcenter_name)` - 查詢工站簡稱
- [x] 5.5 實作 `get_workcenters_by_group(group_name)` - 查詢分組內工站
- [x] 5.6 修改 `_load_workcenter_data()` - 優先使用 SPEC_WORKCENTER_V

## 6. Resource Service - Merged Query

- [x] 6.1 修改 `services/resource_service.py` - import 新快取模組
- [x] 6.2 實作 `get_merged_resource_status()` - 三層快取合併查詢
- [x] 6.3 實作 `get_merged_resource_status()` 的篩選邏輯
  - workcenter_groups 篩選
  - is_production, is_key, is_monitor 篩選
  - status_categories 篩選
- [x] 6.4 實作 `get_resource_status_summary()` - 統計摘要
- [x] 6.5 實作 `get_workcenter_status_matrix()` - 工站狀態矩陣

## 7. API Routes

- [x] 7.1 修改 `routes/resource_routes.py` - 擴充 `/api/resource/status` 使用新查詢
- [x] 7.2 修改 `/api/resource/status/options` - 新增 workcenter_groups, status_categories
- [x] 7.3 新增 `/api/resource/status/summary` endpoint
- [x] 7.4 新增 `/api/resource/status/matrix` endpoint

## 8. Health Check Integration

- [x] 8.1 修改健康檢查 - 新增 equipment_status_cache 狀態
- [x] 8.2 修改健康檢查 - 新增 workcenter_mapping 狀態

## 9. Unit Tests

- [x] 9.1 新增 `tests/test_realtime_equipment_cache.py`
  - test_aggregate_by_resourceid
  - test_classify_status
  - test_get_equipment_status_by_id
- [x] 9.2 新增 `tests/test_workcenter_mapping.py`
  - test_get_workcenter_group
  - test_get_workcenters_by_group
- [x] 9.3 擴充 `tests/test_resource_service.py`
  - test_get_merged_resource_status
  - test_get_merged_resource_status_with_filters
  - test_get_resource_status_summary

## 10. Integration Tests

- [x] 10.1 新增 `tests/e2e/test_realtime_equipment_e2e.py`
  - test_equipment_status_cache_sync
  - test_merged_query_api
  - test_filter_options_include_new_fields

## 11. Documentation & Cleanup

- [x] 11.1 更新 `config/tables.py` - 新增 DW_MES_SPEC_WORKCENTER_V 描述
- [x] 11.2 更新 README 或 API 文件 - 記錄新增 API 與欄位
