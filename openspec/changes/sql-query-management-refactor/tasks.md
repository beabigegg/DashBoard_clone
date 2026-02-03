## 1. 基礎架構設置

- [x] 1.1 建立 `src/mes_dashboard/sql/` 目錄結構
- [x] 1.2 建立 `sql/__init__.py` 匯出公開 API
- [x] 1.3 實作 `sql/loader.py` - SQLLoader 類別
- [x] 1.4 實作 `sql/builder.py` - QueryBuilder 類別
- [x] 1.5 實作 `sql/filters.py` - CommonFilters 類別
- [x] 1.6 更新 `pyproject.toml` 加入 `sql/**/*.sql` 到 package-data
- [x] 1.7 新增 `tests/test_sql_loader.py` 單元測試
- [x] 1.8 新增 `tests/test_sql_builder.py` 單元測試
- [x] 1.9 新增 `tests/test_common_filters.py` 單元測試

## 2. SQL 檔案抽取

- [x] 2.1 建立 `sql/resource/` 目錄
- [x] 2.2 抽取 `resource_service.py` 的 latest_status CTE 到 `resource/latest_status.sql`
- [x] 2.3 抽取 `resource_service.py` 的 status_summary 查詢到 `resource/status_summary.sql`
- [x] 2.4 建立 `sql/dashboard/` 目錄
- [x] 2.5 抽取 `dashboard_service.py` 的 KPI 查詢到 `dashboard/kpi.sql`
- [x] 2.6 抽取 `dashboard_service.py` 的 heatmap 查詢到 `dashboard/heatmap.sql`
- [x] 2.7 建立 `sql/wip/` 目錄
- [x] 2.8 抽取 `wip_service.py` 的 summary 查詢到 `wip/summary.sql`
- [x] 2.9 抽取 `wip_service.py` 的 matrix 查詢到 `wip/matrix.sql`
- [x] 2.10 抽取 `wip_service.py` 的 detail 查詢到 `wip/detail.sql`

## 3. Service 層遷移 - resource_service.py (POC)

- [x] 3.1 重構 `get_resource_latest_status_subquery()` 使用 SQLLoader
- [x] 3.2 重構 `query_resource_status_summary()` 使用 SQLLoader（使用 resource/status_summary.sql）
- [x] 3.3 修復 location filter 的 SQL 注入風險（使用參數化）
- [x] 3.4 修復 asset status filter 的 SQL 注入風險
- [x] 3.5 遷移其餘查詢使用新架構（by_status.sql, by_workcenter.sql, detail.sql, workcenter_status_matrix.sql）
- [x] 3.6 驗證 resource API 功能正確性

## 4. Service 層遷移 - dashboard_service.py

- [x] 4.1 重構 `query_dashboard_kpi()` 使用 SQLLoader（使用 dashboard/kpi.sql）
- [x] 4.2 重構 `query_utilization_heatmap()` 使用 SQLLoader（使用 dashboard/heatmap.sql）
- [x] 4.3 修復 `locations` IN 條件的 SQL 注入風險（已用 QueryBuilder 參數化）
- [x] 4.4 修復 `assetsStatuses` IN 條件的 SQL 注入風險（已用 QueryBuilder 參數化）
- [x] 4.5 修復 workcenter pattern LIKE 條件的萬用字元問題（新增 add_or_like_conditions 方法）
- [x] 4.6 驗證 dashboard API 功能正確性

## 5. Service 層遷移 - resource_history_service.py

- [x] 5.1 建立 `sql/resource_history/` 目錄並抽取 SQL 檔案（kpi.sql, trend.sql, heatmap.sql, detail.sql）
- [x] 5.2 重構 `query_summary()` 使用 SQLLoader（KPI、趨勢、熱圖查詢）
- [x] 5.3 重構 `query_detail()` 使用 SQLLoader
- [x] 5.4 重構 `export_csv()` 使用 SQLLoader
- [x] 5.5 驗證 resource history API 功能正確性

## 6. Service 層遷移 - wip_service.py

- [x] 6.1 重構 `get_wip_summary()` 使用 SQLLoader + QueryBuilder
- [x] 6.2 重構 `get_wip_matrix()` 使用 SQLLoader + QueryBuilder
- [x] 6.3 重構 `get_wip_detail()` 使用 SQLLoader + 分頁參數化
- [x] 6.4 重構搜尋函數（search_workorders, search_lot_ids, search_packages, search_types）使用 QueryBuilder
- [x] 6.5 新增 `_build_base_conditions_builder()` 使用 QueryBuilder 取代舊函數
- [x] 6.6 新增 `_add_hold_type_conditions()` 使用 QueryBuilder 取代 `_build_hold_type_sql_list()`
- [x] 6.7 遷移其餘查詢（hold_detail_summary, hold_detail_distribution, hold_detail_lots, lot_detail）使用新架構
- [x] 6.8 驗證 WIP API 功能正確性（75 unit tests passed + 10 integration tests passed）

## 7. Service 層遷移 - 其餘 Service 檔案

- [x] 7.1 遷移 `realtime_equipment_cache.py` 使用新架構（靜態查詢，無需更動）
- [x] 7.2 遷移 `resource_cache.py` 使用新架構（使用 QueryBuilder + 參數化）
- [x] 7.3 遷移 `filter_cache.py` 使用新架構（靜態查詢，無需更動）
- [x] 7.4 驗證 `excel_query_service.py` 參數化（已有良好實作：表名驗證 + 參數化 IN 條件）
- [x] 7.5 驗證各 cache service 功能正確性（48 tests passed）

## 8. Core 層遷移

- [x] 8.1 整合 `core/utils.py` 的 filter 函數至 `sql/filters.py`（新增 `add_equipment_flag_filters`）
- [x] 8.2 `utils.py` deprecated 函數已標記 DeprecationWarning 並無實際使用（向下相容已確保）
- [x] 8.3 確保 `core/database.py` 的 `read_sql_df()` 所有呼叫點皆傳入 params（已驗證，靜態查詢除外）
- [x] 8.4 遷移 `core/cache_updater.py` 使用新架構（靜態查詢，無需更動）
- [x] 8.5 驗證 core 層功能正確性（74 tests passed）

## 9. 整合測試與清理

- [x] 9.1 執行完整測試套件，確保無回歸（172 passed, 10 skipped）
- [x] 9.2 移除 service 中殘留的舊 SQL 字串（query_workcenter_cards, query_resource_detail_with_job, query_ou_trend 已遷移至 SQLLoader）
- [x] 9.3 移除 `_escape_sql()` 函數及相關舊函數（`_build_base_conditions`, `_build_hold_type_sql_list`, `_get_non_quality_reasons_sql`）
- [x] 9.4 標記 `utils.py` 舊函數為 deprecated（已加入 DeprecationWarning）
- [x] 9.5 更新 `core/database.py` 文件說明新的查詢執行方式
- [x] 9.6 在 `sql/__init__.py` 新增完整的 SQL 模組說明文件
- [x] 9.7 驗證 pyproject.toml 配置 `sql/**/*.sql` 且 SQLLoader 可載入所有 18 個 SQL 檔案
