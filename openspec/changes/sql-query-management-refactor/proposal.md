## Why

目前專案中約有 62 個 SQL 查詢（服務層約 46 個 + core 層約 16 個）分散在 8 個 service 檔案及 core 層中，最大的 `wip_service.py` 達 2,423 行程式碼。SQL 查詢以 f-string 內嵌於 Python 中，導致：維護困難、存在 SQL 注入風險、重複程式碼無法共用。

## What Changes

- **新增 SQL 檔案載入器**：建立 `sql/` 目錄結構，將複雜查詢抽取到獨立 `.sql` 檔案
- **新增安全查詢建構器**：實作 `QueryBuilder` 類別，提供參數化查詢、安全的 IN/LIKE 條件建構
- **整合共用篩選模組**：整合現有 `core/utils.py` 的 filter 邏輯至新的 `sql/filters.py`
- **重構 service 層**：遷移所有 8 個含 SQL 的 service 檔案使用新架構
- **重構 core 層**：遷移 `database.py`、`utils.py`、`cache_updater.py` 的 SQL
- **修復 SQL 注入風險**：將 f-string IN/LIKE 條件改為參數化查詢
- **更新打包設定**：修改 `pyproject.toml` 包含 SQL 檔案

## Non-Goals

- `/api/query_table` 動態查表 API（前端限定 TABLES_CONFIG 清單，後端未強制驗證）
- `resource_routes.py` 中的 SQL（屬於 route 層，維持現狀）
- 動態表名/欄位名的參數化（技術上無法用 bind variable，需另案處理白名單驗證）

## Capabilities

### New Capabilities

- `sql-loader`: SQL 檔案載入與快取機制，支援從 `.sql` 檔案讀取查詢並提供 LRU 快取
- `query-builder`: 安全的動態 SQL 建構器，支援參數化的 IN、LIKE、條件組合
- `common-filters`: 共用篩選條件模組，整合現有 `utils.py` 邏輯，消除重複程式碼

### Modified Capabilities

（無現有 spec 需要修改）

## Impact

- **程式碼變更**：
  - 新增 `src/mes_dashboard/sql/` 目錄（loader.py, builder.py, filters.py）
  - 新增 `src/mes_dashboard/sql/wip/*.sql`、`sql/dashboard/*.sql`、`sql/resource/*.sql`
  - 修改 `pyproject.toml` 加入 `sql/**/*.sql` 到 package-data
  - **Service 層（8 個檔案）**：
    - `services/wip_service.py` (20 個查詢)
    - `services/resource_service.py` (7 個查詢)
    - `services/resource_history_service.py` (6 個查詢)
    - `services/dashboard_service.py` (5 個查詢)
    - `services/realtime_equipment_cache.py`
    - `services/resource_cache.py`
    - `services/filter_cache.py`
    - `services/excel_query_service.py`（已有良好的參數化，僅需驗證）
  - **Core 層**：
    - `core/database.py`：確保所有呼叫皆傳入 params
    - `core/utils.py`：整合 filter 邏輯至 sql/filters.py
    - `core/cache_updater.py`

- **API 影響**：無，僅內部實作變更

- **依賴**：無新增依賴，使用現有的 SQLAlchemy + oracledb

- **測試**：需新增 `tests/test_sql_builder.py`、`tests/test_sql_loader.py`、`tests/test_common_filters.py`
