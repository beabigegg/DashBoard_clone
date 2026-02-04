## ADDED Requirements

### Requirement: 統一成功回應格式

系統 SHALL 對所有成功的 API 回應使用統一的 envelope 格式。

#### Scenario: 成功回應包含 success 標記
- **WHEN** API 請求成功執行
- **THEN** 回應 body SHALL 包含 `"success": true`
- **AND** 原有回應資料 SHALL 放在 `data` 欄位中

#### Scenario: 成功回應範例
- **WHEN** 呼叫 `GET /api/dashboard/kpi` 成功
- **THEN** 回應格式 SHALL 為：
  ```json
  {
    "success": true,
    "data": {
      "total": 100,
      "prd": 50,
      ...
    }
  }
  ```

---

### Requirement: 統一錯誤回應格式

系統 SHALL 對所有失敗的 API 回應使用統一的錯誤格式。

#### Scenario: 錯誤回應包含錯誤代碼
- **WHEN** API 請求執行失敗
- **THEN** 回應 body SHALL 包含 `"success": false`
- **AND** SHALL 包含 `error` 物件
- **AND** `error.code` SHALL 為機器可讀的錯誤代碼
- **AND** `error.message` SHALL 為使用者友善的中文訊息

#### Scenario: 錯誤回應範例
- **WHEN** 資料庫連線失敗
- **THEN** 回應格式 SHALL 為：
  ```json
  {
    "success": false,
    "error": {
      "code": "DB_CONNECTION_FAILED",
      "message": "資料庫連線失敗，請稍後再試"
    }
  }
  ```

#### Scenario: 開發模式顯示詳細錯誤
- **WHEN** `FLASK_ENV=development`
- **AND** API 請求執行失敗
- **THEN** `error` 物件 SHALL 額外包含 `details` 欄位
- **AND** `details` SHALL 包含技術性錯誤訊息（如 ORA-xxxxx）

#### Scenario: 生產模式隱藏詳細錯誤
- **WHEN** `FLASK_ENV=production`
- **AND** API 請求執行失敗
- **THEN** `error` 物件 SHALL NOT 包含 `details` 欄位

---

### Requirement: 標準錯誤代碼

系統 SHALL 定義並使用標準化的錯誤代碼。

#### Scenario: 資料庫相關錯誤代碼
- **WHEN** 資料庫連線失敗
- **THEN** 錯誤代碼 SHALL 為 `DB_CONNECTION_FAILED`

#### Scenario: 資料庫查詢逾時
- **WHEN** 資料庫查詢超過 55 秒
- **THEN** 錯誤代碼 SHALL 為 `DB_QUERY_TIMEOUT`

#### Scenario: 熔斷器開啟
- **WHEN** Circuit Breaker 處於 OPEN 狀態
- **THEN** 錯誤代碼 SHALL 為 `SERVICE_UNAVAILABLE`

#### Scenario: 驗證失敗
- **WHEN** 請求參數驗證失敗
- **THEN** 錯誤代碼 SHALL 為 `VALIDATION_ERROR`

#### Scenario: 未授權
- **WHEN** 使用者未登入或 session 過期
- **THEN** 錯誤代碼 SHALL 為 `UNAUTHORIZED`

#### Scenario: 禁止存取
- **WHEN** 使用者權限不足
- **THEN** 錯誤代碼 SHALL 為 `FORBIDDEN`

---

### Requirement: 全域錯誤處理

系統 SHALL 在 middleware 層級統一處理所有未捕獲的錯誤。

#### Scenario: 認證中介層拒絕
- **WHEN** 認證中介層（`create_app` 中的 `@app.before_request`）拒絕請求
- **THEN** 回應格式 SHALL 符合統一錯誤格式
- **AND** 錯誤代碼 SHALL 為 `UNAUTHORIZED` 或 `FORBIDDEN`

#### Scenario: 未處理的例外
- **WHEN** 路由處理器拋出未捕獲的例外
- **THEN** Flask 錯誤處理器 SHALL 攔截該例外
- **AND** 回應格式 SHALL 符合統一錯誤格式
- **AND** 錯誤代碼 SHALL 為 `INTERNAL_ERROR`

#### Scenario: 404 錯誤處理
- **WHEN** 請求的路由不存在
- **THEN** 回應格式 SHALL 符合統一錯誤格式
- **AND** 錯誤代碼 SHALL 為 `NOT_FOUND`

#### Scenario: 全域錯誤處理器註冊
- **WHEN** Flask 應用程式初始化
- **THEN** `create_app()` SHALL 註冊以下錯誤處理器：
  - `@app.errorhandler(401)` - 處理未授權
  - `@app.errorhandler(403)` - 處理禁止存取
  - `@app.errorhandler(404)` - 處理找不到資源
  - `@app.errorhandler(500)` - 處理伺服器錯誤
  - `@app.errorhandler(Exception)` - 處理所有未捕獲例外

---

### Requirement: 向下相容

系統 SHALL 維持與現有 API 的向下相容性。

#### Scenario: 原有欄位保留
- **WHEN** 使用新的回應格式
- **THEN** 原有 API 回傳的欄位 SHALL 完整保留在 `data` 中
- **AND** 欄位名稱與型別 SHALL 不變

#### Scenario: HTTP 狀態碼維持
- **WHEN** API 回應使用新格式
- **THEN** HTTP 狀態碼 SHALL 維持原有語義
- **AND** 成功 SHALL 回傳 2xx
- **AND** 客戶端錯誤 SHALL 回傳 4xx
- **AND** 伺服器錯誤 SHALL 回傳 5xx
