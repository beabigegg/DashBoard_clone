## Why

目前專案的 API 回應格式與路由慣例存在長期累積的不一致：雖已提供 `core/response.py`，但多數路由仍手動 `jsonify`，前端與測試也同時依賴多種錯誤格式。這使得新功能迭代時容易產生行為漂移，且讓跨頁 API 重用、錯誤處理、監控治理成本持續上升。

## What Changes

- 建立並落地「API 回應契約統一」的遷移治理方案，將 `api_development_contract.md` 定義為目標狀態，並以分階段方式實作。
- 定義全域 API 回應 envelope 與錯誤碼規範（`success/data/meta`、`success/error/meta`）及 helper 強制使用規則。
- 納入「特例端點治理」：明確定義 `/health*` 與串流/下載類端點的契約例外與邊界。
- 定義「前後端相容遷移路徑」：在全面轉換前，先處理前端對 `error` 字串格式與 `cache_expired/cache_miss` 特判的相容需求。
- 以風險導向分批重構：第一批 `wip_routes.py`，後續擴展至高流量路由與 `app.py` 內 legacy API。
- **BREAKING**：最終目標狀態下，舊式 `{"success": false, "error": "..."}` 將被 `{"success": false, "error": {"code": "...", "message": "..."}}` 取代（採分階段切換，不一次性破壞）。

## Capabilities

### New Capabilities
- `api-response-contract-unification`: 定義並治理全站 API 回應契約、例外端點邊界、遷移順序與驗收標準。

### Modified Capabilities
- `api-safety-hygiene`: 擴充 API route hygiene 要求，新增「路由回應 helper 使用治理與例外清單」要求。
- `shell-health-summary-detail`: 明確化 health endpoints 在契約統一過程中的相容責任與不可破壞輸出需求。

## Impact

- Affected backend:
  - `src/mes_dashboard/routes/*_routes.py`（目前約 405 個 `jsonify` 呼叫）
  - `src/mes_dashboard/app.py` 內 legacy API 端點（`/api/query_table`, `/api/get_table_columns`, `/api/get_table_info`, `/api/portal/navigation`）
  - `src/mes_dashboard/core/response.py`（補齊 helper 與錯誤碼分類）
- Affected frontend:
  - `frontend/src/core/api.js`
  - 多個頁面 `unwrapApiResult` 與 `cache_expired/cache_miss` 判斷路徑
- Affected tests:
  - 後端 route tests（多處目前直接斷言 `payload['error']` 為字串）
  - 前端與 e2e 測試中對錯誤 payload 的既有假設
- Operational / governance:
  - `/health`, `/health/deep`, `/health/frontend-shell`, `/admin/api/*` 的監控與 UI 依賴需保留契約穩定
  - 需建立 endpoint 分類清單與 rollout gate，避免一次性大改造成回歸風險
