# MES Dashboard - API 重構計畫 (v1.0)

##### **1. 目標與策略**

本計畫的目標是將專案中所有 API 端點的實現，統一至 `api_development_contract.md` 所定義的規範。

我們採用**漸進式重構策略**：
*   **立即生效**：所有**新開發**的 API 端點必須嚴格遵守新契約。
*   **分批修復**：對於既有端點，我們將分批次、按優先級進行重構。

---

##### **2. 重構任務**

###### **任務 1: `wip_routes.py` 重構 (高優先級)**

*   **目標**：將此核心模組中所有手動的 `jsonify` 呼叫，替換為 `core/response.py` 的輔助函式。
*   **執行步驟**：
    1.  在檔案頂部引入所需函式：`from mes_dashboard.core.response import success_response, validation_error, not_found_error, internal_error`。
    2.  將 `return jsonify({'success': True, 'data': result})` 替換為 `return success_response(result)`。
    3.  將 `return jsonify({'success': False, 'error': 'Invalid status...'}), 400` 替換為 `return validation_error('Invalid status...')`。
    4.  將 `return jsonify({'success': False, 'error': '查詢失敗'}), 500` 替換為 `return internal_error()`。可以的話，根據上下文替換為更精確的錯誤，例如 `db_query_error()`。
    5.  將 `return jsonify({'success': False, 'error': '找不到此批號'}), 404` 替換為 `return not_found_error('找不到此批號')`。

###### **任務 2: `health_routes.py` 處理 (中優先級)**

*   **目標**：評估並決定此特殊端點的處理方式。
*   **執行步驟**：
    1.  **評估依賴**：確認是否有外部的監控系統（如 Prometheus, Datadog）正在使用 `/health` 或 `/health/deep` 端點，並且依賴其目前**完全自訂**的 JSON 結構。
    2.  **決策與執行**：
        *   **如果存在外部依賴**：我們應將此端點視為一個**特例**。在契約文件中明確標註 `health_routes.py` 因外部整合需求，可不遵循標準回應外層 (envelope)，但內部仍應盡可能使用標準的錯誤處理邏輯。
        *   **如果不存在外部依賴**：為了內部一致性，應進行重構。將其巨大的回應內容整個作為 `data` 欄位的值，並用 `success_response` 包裝。
            *   **範例**: `return success_response({ 'status': status, 'services': services, ... })`。

###### **任務 3: 審計並重構其餘所有路由檔案 (持續性任務)**

*   **目標**：將契約規範應用於專案的所有 API 端點。
*   **執行步驟**：
    1.  建立一個包含所有路由檔案的檢查清單。
    2.  按照「順便重構」原則，或在團隊有空閒時間時，逐一對清單中的檔案執行與「任務 1」相同的重構步驟。
    *   **檢查清單**:
        *   [ ] `admin_routes.py`
        *   [ ] `auth_routes.py`
        *   [ ] `dashboard_routes.py`
        *   [ ] `excel_query_routes.py`
        *   [ ] `hold_history_routes.py`
        *   [ ] `hold_overview_routes.py`
        *   [ ] `hold_routes.py`
        *   [ ] (依此類推，列出所有檔案)