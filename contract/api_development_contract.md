### **MES Dashboard - 後端 API 開發契約規範 (v1.1)**

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

---

#### **6. API 盤點清單同步治理 (API Inventory Governance)**

**原則：API 契約盤點必須可追蹤且與實際路由同步。**

*   **契約 6.1**: `contract/api_inventory.md` 為 API 契約治理盤點清單，記錄端點分類與例外邊界。
*   **契約 6.2**: 若有新增、刪除、重新命名、搬移任何 API 端點（包含 `routes/*.py` 與 `app.py` 的 `/api/*` bridge 端點），必須在**同一個變更**同步更新 `contract/api_inventory.md`。
*   **契約 6.3**: 每個 API 端點都必須被分類為 `standard-json`、`health-exception`、`stream-download-exception` 或 `legacy-transition` 之一。
*   **契約 6.4**: 新增或變更例外端點時，必須在盤點清單補上例外原因、影響範圍與對應驗證（測試或檢查機制）說明。

---

#### **7. 測試層次定位 (Test Tier Positioning)**

本節說明三個測試層次的職責邊界，避免 happy path、resilience 與 fault 測試混入同一檔。

| 層次 | 目錄 | 觸發時機 | 覆蓋範圍 |
|------|------|----------|----------|
| **Resilience (韌性)** | `frontend/tests/playwright/resilience/` | pre-merge CI gate | API failure 注入（500/503/abort）、慢網路 overlay 行為、按鈕連點防重複、瀏覽器歷史 URL state 回復 |
| **Data Boundary (資料邊界)** | `frontend/tests/playwright/data-boundary/` | pre-merge CI gate | 惡意輸入（SQL、100k 字串、Unicode、倒置日期）、空結果的 empty-state 顯示、匯出按鈕 disabled |
| **Fault Integration (故障整合)** | `tests/integration/test_oracle_error_codes.py`, `test_redis_timeout_fallback.py`, `test_race_conditions.py` | nightly `--run-integration-real` | ORA-* 錯誤碼對應、Redis timeout fallback、race condition 並發競態 |

**契約 7.1**：Happy path 契約驗證（既有 route tests、Vitest composables）不得混入 resilience / fault 情境。新增的 resilience / data-boundary / fault 測試必須放在對應子目錄，並以獨立 spec/file 呈現。

**契約 7.2**：每個新 resilience 或 fault test 必須執行 **mutation check**（移除對應 handler → spec 應 FAIL），確認測試真的在偵測錯誤路徑，而非形式驗證。PR 描述應附 mutation check 紀錄。

**契約 7.3**：Route 層 fuzz 測試（`tests/routes/test_fuzz_routes.py`）使用 `MALICIOUS_INPUTS` 常數（定義於 `tests/routes/_fuzz_payloads.py`）確保所有接受查詢條件的 API 端點對惡意 payload 以 `VALIDATION_ERROR` 回應而非 500。
