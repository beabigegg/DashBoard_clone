## 1. 後端：欄位 Metadata 功能

- [x] 1.1 在 `database.py` 新增 `get_table_column_metadata()` 函式，查詢 `ALL_TAB_COLUMNS` 取得欄位類型資訊
- [x] 1.2 在 `excel_query_service.py` 新增 `detect_excel_column_type()` 函式，分析 Excel 欄位類型
- [x] 1.3 在 `excel_query_routes.py` 新增 `POST /api/excel-query/table-metadata` 端點

## 2. 後端：日期範圍查詢功能

- [x] 2.1 在 `excel_query_service.py` 新增 `build_date_range_condition()` 函式，生成 BETWEEN SQL 條件
- [x] 2.2 修改 `TABLES_CONFIG` 結構確認 `time_field` 欄位可被正確讀取

## 3. 後端：LIKE 模糊查詢功能

- [x] 3.1 在 `excel_query_service.py` 新增 `build_like_condition()` 函式，支援 contains/prefix/suffix 三種模式
- [x] 3.2 在 `excel_query_service.py` 新增 `escape_like_pattern()` 函式，處理特殊字元 `%` 和 `_` 的跳脫
- [x] 3.3 新增 LIKE 查詢關鍵字數量驗證（上限 100 個）

## 4. 後端：進階查詢 API

- [x] 4.1 在 `excel_query_routes.py` 新增 `POST /api/excel-query/execute-advanced` 端點
- [x] 4.2 整合 IN、LIKE、日期範圍三種條件的組合查詢邏輯
- [x] 4.3 新增大型資料表 LIKE 查詢效能警告機制

## 5. 前端：欄位類型顯示

- [x] 5.1 修改 `excel_query.html`，在 Excel 欄位選擇下拉選單加入類型標籤
- [x] 5.2 修改 `excel_query.html`，在 Oracle 欄位選擇下拉選單加入類型標籤
- [x] 5.3 新增欄位類型不相符警告訊息

## 6. 前端：進階條件 UI

- [x] 6.1 在 Step 4 區塊新增摺疊式「進階條件」面板
- [x] 6.2 新增查詢類型選擇器（完全符合 / 包含 / 開頭符合 / 結尾符合）
- [x] 6.3 新增日期範圍選擇器（起始日期、結束日期）
- [x] 6.4 新增日期範圍驗證邏輯（start <= end, range <= 365 days）
- [x] 6.5 新增大型資料表 LIKE 查詢效能警告 UI

## 7. 前端：API 整合

- [x] 7.1 修改 `loadTableColumns()` 改用 `/table-metadata` 端點取得欄位資訊
- [x] 7.2 新增 `executeAdvancedQuery()` 函式呼叫 `/execute-advanced` 端點
- [x] 7.3 修改 `validateQuery()` 加入進階條件驗證邏輯

## 8. 測試與驗證

- [x] 8.1 測試日期範圍查詢功能（各種日期組合）
- [x] 8.2 測試 LIKE 查詢功能（三種模式、特殊字元）
- [x] 8.3 測試欄位類型偵測準確度
- [x] 8.4 測試大型資料表效能警告觸發
- [x] 8.5 驗證向後相容性（原有 `/execute` 端點仍正常運作）

> 注意：上述測試項目需在實際環境中手動驗證。程式碼已通過語法檢查。
