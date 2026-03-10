### **MES Dashboard - 後端 API 開發契約規範 (v1.0)**

#### **1. 目的**

為建立一套可預測、易於維護、且對前後端開發人員都友善的 API 標準，本契約定義了所有後端 API 在回應格式、錯誤處理、路由設計等方面的統一規範。所有新的 API 開發與既有 API 的重構都必須遵守此契約。

---

#### **2. 回應格式 (Response Format)**

*   **契約 2.1 (禁止手動建立回應)**：**嚴格禁止**在路由處理函式中手動使用 `jsonify` 來建立回應。
*   **契約 2.2 (統一使用輔助函式)**：所有 API 回應都**必須**使用 `src/mes_dashboard/core/response.py` 中提供的 `success_response` 和 `error_response` 系列輔助函式來產生。

*   **契約 2.3 (成功回應結構)**：所有成功的 (`2xx`) 回應，其 JSON 主體必須遵循以下結構：
    ```json
    {
      "success": true,
      "data": <Payload>,
      "meta": {
        "timestamp": "<ISO 8601 UTC Timestamp>",
        ...
      }
    }
    ```
    *   `<Payload>`: 核心資料，可以是物件或陣列。
    *   `meta`: 包含時間戳及其他可選的元數據（如分頁資訊、快取狀態）。

*   **契約 2.4 (錯誤回應結構)**：所有失敗的 (`4xx`, `5xx`) 回應，其 JSON 主體必須遵循以下結構：
    ```json
    {
      "success": false,
      "error": {
        "code": "<ERROR_CODE_STRING>",
        "message": "<User-friendly error message>",
        "details": "<Technical details, ONLY in development mode>"
      },
      "meta": {
        "timestamp": "<ISO 8601 UTC Timestamp>"
      }
    }
    ```
    *   `code`: 供機器讀取的、標準化的錯誤碼字串。
    *   `message`: 對終端使用者友善、可直接顯示的錯誤訊息。

---

#### **3. 錯誤處理 (Error Handling)**

*   **契約 3.1 (使用標準錯誤碼)**：`error.code` **必須**使用 `core/response.py` 中預定義的標準錯誤碼常數（例如 `VALIDATION_ERROR`, `NOT_FOUND`, `DB_QUERY_ERROR`）。若需新增錯誤碼，需經團隊討論。

*   **契約 3.2 (優先使用便捷函式)**：應**優先**使用 `core/response.py` 中針對特定情境封裝的便捷函式，例如 `validation_error()`, `not_found_error()`, `internal_error()`，而不是直接呼叫 `error_response()`。

---

#### **4. 路由與命名 (Routing & Naming)**

*   **契約 4.1 (藍圖化)**：所有 API 路由**必須**按功能模組劃分，並在獨立的 Flask Blueprint 檔案中進行管理。
*   **契約 4.2 (URL 前綴)**：所有 API 路由的 URL **必須**以 `/api/` 作為根路徑。
*   **契約 4.3 (命名慣例)**：
    *   對於獲取**資源**的端點，應使用名詞和 HTTP 方法 (RESTful 風格)，例如 `GET /api/wip/lot/<lotid>`。
    *   對於執行**特定操作**的端點，可以使用動詞 (RPC 風格)，例如 `POST /api/auth/login` 或 `GET /api/wip/overview/summary`。
    *   保持風格一致性。

---

#### **5. 關注點分離 (Separation of Concerns)**

*   **契約 5.1 (保持控制器輕薄)**：路由處理函式（控制器）應保持「輕薄」。其職責僅限於：
    1.  解析 HTTP 請求（路徑參數、查詢參數、請求主體）。
    2.  對輸入進行基礎驗證。
    3.  呼叫對應的服務層 (Service Layer) 函式來執行業務邏輯。
    4.  使用 `core/response.py` 的輔助函式來格式化並回傳最終結果。
*   **契約 5.2**：**嚴禁**在路由處理函式中撰寫複雜的業務邏輯或直接進行資料庫操作。