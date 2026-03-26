## 1. Baseline and Scope Governance

- [x] 1.1 盤點所有 API endpoints，建立分類清單（`standard-json` / `health-exception` / `stream-download-exception` / `legacy-transition`）
- [x] 1.2 建立遷移基線報告：統計 `routes` 與 `app.py` 中手動 `jsonify` 呼叫數、舊式 `error` 字串回應數
- [x] 1.3 定義第一波與後續波次清單（至少包含 Wave A: `wip_routes.py`）並寫入 change 附錄或執行紀錄

## 2. Response Helper and Error Code Hardening

- [x] 2.1 擴充 `src/mes_dashboard/core/response.py`：補齊遷移所需錯誤碼與便捷 helper（含 cache 類錯誤碼）
- [x] 2.2 確認 `success_response` / `error_response` metadata 欄位契約一致（timestamp、retry 等）
- [x] 2.3 建立 helper 使用指引（validation/not-found/internal/degraded 場景對應）

## 3. Wave A Backend Migration (`wip_routes.py`)

- [x] 3.1 將 `wip_routes.py` 成功回應改為 `success_response(...)`
- [x] 3.2 將 `wip_routes.py` 錯誤回應改為 `validation_error(...)` / `not_found_error(...)` / `internal_error(...)`
- [x] 3.3 移除 `wip_routes.py` 中手動 `jsonify` 回應建構（保留必要 Flask request parsing）
- [x] 3.4 驗證既有 rate-limit 行為與錯誤碼一致性（429 + Retry-After）

## 4. Exception Endpoint Guardrails

- [x] 4.1 為 `/health`, `/health/deep`, `/health/frontend-shell` 建立契約例外註記與保護規則
- [x] 4.2 稽核 CSV/NDJSON/檔案下載端點：成功回應保留串流格式，錯誤回應統一 error envelope
- [x] 4.3 定義 `app.py` legacy API（`/api/query_table`, `/api/get_table_columns`, `/api/get_table_info`, `/api/portal/navigation`）過渡策略

## 5. Frontend Compatibility Migration

- [x] 5.1 更新 `frontend/src/core/api.js` 錯誤正規化策略：優先 `error.code/error.message`，保留舊字串相容
- [x] 5.2 逐頁調整 `unwrapApiResult` 與 `cache_expired/cache_miss` 判斷，改以 error code 為主
- [x] 5.3 確保 admin / portal shell / report pages 在 Wave A 後可無回歸運作

## 6. Test and Contract Verification

- [x] 6.1 更新 `tests/test_wip_routes.py`、`tests/test_api_integration.py` 以符合新 error envelope
- [x] 6.2 補充 health exception 合約測試，鎖定 top-level payload 不被 envelope 化
- [x] 6.3 補充或新增契約檢查測試：禁止在 standard-json scope 新增手動 `jsonify`
- [x] 6.4 新增遷移趨勢驗證：legacy `jsonify` 計數不得回升

## 7. Documentation and Rollout

- [x] 7.1 更新 `contract/api_refactoring_plan.md`，改為分波遷移版（含例外端點與驗收條件）
- [x] 7.2 更新開發文件，明確說明 API 契約與 helper 使用規範
- [x] 7.3 產出 Wave A 完成報告（變更清單、測試結果、回滾點）
- [x] 7.4 定義 Wave B+ 啟動條件與風險門檻
