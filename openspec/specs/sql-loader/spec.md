## Requirements

### Requirement: SQL 檔案載入

系統 SHALL 提供 `SQLLoader` 類別，從 `.sql` 檔案載入 SQL 查詢字串。

#### Scenario: 載入存在的 SQL 檔案
- **WHEN** 呼叫 `SQLLoader.load("wip/summary")`
- **THEN** 系統回傳 `sql/wip/summary.sql` 檔案的完整內容

#### Scenario: 載入不存在的 SQL 檔案
- **WHEN** 呼叫 `SQLLoader.load("nonexistent/query")`
- **THEN** 系統拋出 `FileNotFoundError` 並包含檔案路徑

### Requirement: SQL 檔案快取

系統 SHALL 使用 LRU cache 快取已載入的 SQL 檔案內容，避免重複讀取檔案系統。

#### Scenario: 重複載入相同檔案使用快取
- **WHEN** 連續呼叫 `SQLLoader.load("wip/summary")` 兩次
- **THEN** 第二次呼叫從記憶體快取取得，不重新讀取檔案

#### Scenario: 快取容量限制
- **WHEN** 快取達到 100 個條目上限
- **THEN** 系統自動移除最少使用的條目

### Requirement: 結構性參數替換

系統 SHALL 提供 `load_with_params()` 方法，支援 Jinja2 風格的結構性參數替換（僅用於非使用者輸入的結構性參數）。

#### Scenario: 替換結構性參數
- **WHEN** SQL 檔案內容為 `SELECT * FROM {{ table_name }}`
- **AND** 呼叫 `SQLLoader.load_with_params("query", table_name="DWH.MY_TABLE")`
- **THEN** 系統回傳 `SELECT * FROM DWH.MY_TABLE`

#### Scenario: 未提供的參數保持原樣
- **WHEN** SQL 檔案內容為 `SELECT * FROM {{ table_name }} {{ WHERE_CLAUSE }}`
- **AND** 呼叫 `SQLLoader.load_with_params("query", table_name="T")`
- **THEN** 系統回傳 `SELECT * FROM T {{ WHERE_CLAUSE }}`
