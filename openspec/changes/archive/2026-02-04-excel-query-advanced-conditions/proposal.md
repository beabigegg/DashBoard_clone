## Why

現有 Excel 批次查詢功能僅支援 `WHERE column IN (...)` 精確比對，無法滿足以下常見查詢需求：
1. 歷史資料表動輒數千萬筆，缺乏日期範圍篩選導致查詢效能低落或 timeout
2. 無法進行模糊比對（如搜尋包含特定關鍵字的批號）
3. 使用者需手動判斷欄位類型，容易選錯查詢欄位

## What Changes

- **新增日期範圍查詢**：自動識別時間欄位，支援起訖日期篩選，與 IN 條件組合使用
- **新增 LIKE 模糊查詢**：支援「包含」、「開頭符合」、「結尾符合」三種模式
- **新增欄位類型偵測**：
  - Excel 欄位：自動分析樣本值判斷 text/number/date/id 類型
  - Oracle 欄位：查詢 `ALL_TAB_COLUMNS` 取得欄位 metadata（DATA_TYPE, DATA_LENGTH 等）
  - 前端顯示欄位類型標籤，輔助使用者選擇正確欄位
- **新增進階查詢 API**：整合上述功能的新端點 `/api/excel-query/execute-advanced`
- **效能防護機制**：
  - LIKE 包含查詢限制最多 100 個關鍵字
  - 大型表（>10M）使用 LIKE 時顯示效能警告
  - 日期範圍預設 90 天，最大 365 天

## Capabilities

### New Capabilities
- `excel-query-date-range`: 日期範圍篩選功能，支援時間欄位自動識別與 BETWEEN 條件
- `excel-query-like-search`: LIKE 模糊查詢功能，支援包含/前綴/後綴三種模式
- `excel-query-column-metadata`: 欄位類型偵測與顯示，包含 Excel 與 Oracle 欄位分析

### Modified Capabilities
（無現有 spec 需修改）

## Impact

### 程式碼變更
- `src/mes_dashboard/routes/excel_query_routes.py`：新增 `/table-metadata`、`/execute-advanced` 端點
- `src/mes_dashboard/services/excel_query_service.py`：新增日期/LIKE 條件生成函式
- `src/mes_dashboard/core/database.py`：新增 `get_table_column_metadata()` 函式
- `src/mes_dashboard/templates/excel_query.html`：新增查詢類型選擇、日期選擇器、欄位類型標籤

### API 變更
- 新增 `POST /api/excel-query/table-metadata`
- 新增 `POST /api/excel-query/execute-advanced`
- 現有端點維持不變（向後相容）

### 相依套件
- 無新增套件（使用現有 pandas, oracledb）

### 效能考量
- LIKE `%keyword%` 無法使用索引，需限制使用範圍
- 日期範圍查詢可利用時間欄位索引，效能良好
