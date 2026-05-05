---
contract: api
summary: API behavior, compatibility rules, and endpoint contract requirements.
owner: application-team
surface: api
schema-version: 1.1.0
last-changed: 2026-05-05
breaking-change-policy: deprecate-2-minors
---

# API Contract — MES Dashboard

> 來源：遷移自 `contract/api_development_contract.md` v1.1（2026-05-05）

## 1. API Style

- **Response style:** 所有 API 回應必須使用 `core/response.py` 提供的 `success_response` / `error_response` 輔助函式；禁止手動 `jsonify`。
- **Error style:** 見 `contracts/api/error-format.md`；`error.code` 必須使用預定義的標準錯誤碼常數。
- **Auth style:** Session cookie（Flask-Session）；需要認證的端點使用 `login_required` 裝飾器；Admin 端點額外驗證 `is_admin` flag。
- **Pagination style:** 以 `page` / `per_page` 查詢參數控制；回應在 `meta` 物件中附帶分頁資訊。
- **Date/time style:** ISO 8601 UTC（`meta.timestamp`）；查詢參數日期格式為 `YYYY-MM-DD`。

## 2. Response Envelope

### 2.1 成功回應 (2xx)

```json
{
  "success": true,
  "data": "<Payload>",
  "meta": {
    "timestamp": "<ISO 8601 UTC>",
    "app_version": "<string>",
    "...": "其他可選 meta 欄位（cache_state、pagination 等）"
  }
}
```

- `data`：核心 payload，可為物件或陣列。
- `meta.app_version`：每個 `success_response` / `error_response` 自動注入，來源為 `APP_VERSION` env 或 package metadata。

### 2.2 錯誤回應 (4xx / 5xx)

```json
{
  "success": false,
  "error": {
    "code": "<ERROR_CODE_STRING>",
    "message": "<User-friendly message>",
    "details": "<development-only technical details>"
  },
  "meta": {
    "timestamp": "<ISO 8601 UTC>"
  }
}
```

## 3. Error Handling

| 契約 | 規則 |
|---|---|
| 3.1 | `error.code` 必須使用 `core/response.py` 預定義常數（`VALIDATION_ERROR`、`NOT_FOUND`、`DB_QUERY_ERROR` 等） |
| 3.2 | 優先使用便捷函式：`validation_error()`、`not_found_error()`、`internal_error()` 等 |

## 4. Endpoint Requirements

> GET+POST 端點（為避免 URL 過長而同時接受 POST JSON body）在下表中以 GET 代表；詳見 api-inventory.md。

| method | path | auth | request schema | response schema | errors | tests |
|---|---|---|---|---|---|---|
| GET | /api/wip/overview/summary | required | query params | success_response | 400/500 | route tests |
| POST | /api/wip/overview/summary | required | JSON body | success_response | 400/500 | route tests |
| GET | /api/hold/overview | required | query params | success_response | 400/500 | route tests |
| POST | /api/hold-history/today-snapshot | required | JSON body | success_response | 400/503 | e2e tests |
| POST | /api/reject-history/query | required | JSON body | success_response | 202/400/500 | route tests |
| GET | /api/reject-history/job/<job_id> | required | — | success_response | 404 | route tests |
| POST | /api/resource/history/query | required | JSON body | success_response | 400/410/500 | route tests |
| POST | /api/yield-alert/query | required | JSON body | success_response | 202/400/500 | route tests |
| GET | /api/yield-alert/cross-filter-options | required | query params | success_response | 400/410 | route tests |
| POST | /api/production-history/query | required | JSON body | success_response | 202/400/503 | route tests |
| POST | /api/production-history/page | required | JSON body | success_response | 400/410 | route tests |
| GET | /api/production-history/export | required | query params | csv-stream | 400/410 | e2e tests |
| POST | /api/trace/lineage | required | JSON body | success_response | 202/400/500 | route tests |
| GET | /api/trace/lineage/job/<job_id> | required | — | success_response | 404 | route tests |
| GET | /api/mid-section-defect/analysis | required | query params | success_response | 400/500 | route tests |
| POST | /api/material-trace/query | required | JSON body | success_response | 202/400/503 | route tests |
| POST | /api/material-trace/export | required | JSON body | csv-stream | 400/409 | e2e tests |
| GET | /api/analytics/anomaly-summary | required | query params | success_response | 400/503 | route tests |
| POST | /api/auth/login | public | JSON body | success_response | 400/401/429 | route tests |
| POST | /api/auth/logout | public | — | success_response | — | route tests |
| GET | /api/auth/me | public | — | success_response | — | route tests |
| PATCH | /api/auth/heartbeat | required | — | success_response | 401 | route tests |
| POST | /api/ai/query | required | JSON body | success_response | 400/500 | route tests |
| GET | /api/job/<job_id> | required | query params | success_response | 400/404 | route tests |
| POST | /api/job/<job_id>/abandon | required | JSON body | success_response | 403/404/409 | route tests |
| POST | /api/admin/analytics/recalculate | admin | — | success_response | 403/500 | route tests |
| GET | /admin/api/user-usage-kpi | admin | query params | success_response | 400/403 | route tests |
| GET | /health | none | — | health-payload | — | smoke tests |
| GET | /health/deep | none | — | health-payload | — | smoke tests |
| GET | /api/spool/<namespace>/<query_id>.parquet | required | — | parquet-binary | 404/410 | route tests |

## 5. Routing & Naming

- **4.1 Blueprint：** 所有 API 路由必須按功能模組劃分為獨立 Flask Blueprint 檔案。
- **4.2 URL Prefix：** 所有 API 路由 URL 必須以 `/api/` 作為根路徑。
- **4.3 Naming：** 資源端點用名詞+HTTP method（RESTful）；操作端點可用動詞（RPC 風格）；保持風格一致性。

## 6. Separation of Concerns

- **5.1 Thin Controller：** 路由 handler 只負責：解析請求、基礎驗證、呼叫 service、格式化回應。
- **5.2：** 禁止在路由 handler 中撰寫業務邏輯或直接操作 DB。

## 7. Async Job Pattern

**Type A — 同步 re-query on 410：** view miss → 410 `cache_expired` → client 同步重新觸發 `execute_primary_query()`。適用：`hold_history_routes.py`、`resource_history_routes.py`。

**Type B — async 202 polling：** query miss + RQ available → 202 `{async: true, job_id, status_url}` → client polling `GET /api/job/<job_id>?prefix=<p>`。RQ 不可用時 fallback sync 200。適用：`reject_history_routes.py`、`yield_alert_routes.py`、`production_history_routes.py`、`trace_routes.py`、`material_trace_routes.py`。

## 8. API Inventory Governance

- **6.1：** `contracts/api/api-inventory.md` 為 API 契約治理盤點清單，記錄端點分類與例外邊界。
- **6.2：** 新增/刪除/重新命名/搬移任何 API 端點，必須在同一個變更同步更新盤點清單。
- **6.3：** 每個端點必須被分類為 `standard-json`、`health-exception`、`stream-download-exception` 或 `legacy-transition`。
- **6.4：** 例外端點更新時必須補上原因、影響範圍與對應驗證說明。

## 9. Test Tier Positioning

- **Resilience**（`frontend/tests/playwright/resilience/`，pre-merge CI）：API failure 注入（500/503/abort）、慢網路 overlay 行為、按鈕連點防重複、瀏覽器歷史 URL state 回復。
- **Data Boundary**（`frontend/tests/playwright/data-boundary/`，pre-merge CI）：惡意輸入（SQL、100k 字串、Unicode、倒置日期）、empty-state 顯示、export 按鈕 disabled。
- **Fault Integration**（`tests/integration/test_oracle_error_codes.py` 等，nightly）：ORA-* 錯誤碼對應、Redis timeout fallback、race condition 並發競態。

規則：
- **7.1：** Happy path 契約驗證不得混入 resilience/fault 情境；新增測試必須放在對應子目錄以獨立 spec/file 呈現。
- **7.2：** 每個 resilience/fault test 必須執行 mutation check（移除對應 handler → spec 應 FAIL）；PR 描述附 mutation check 紀錄。
- **7.3：** Route fuzz 測試（`tests/routes/test_fuzz_routes.py`）使用 `MALICIOUS_INPUTS`（定義於 `tests/routes/_fuzz_payloads.py`），惡意 payload 必須以 `VALIDATION_ERROR` 回應而非 500。

## 10. Compatibility Notes

- `meta.app_version`（2026-04-15）：所有 `success_response` / `error_response` 自動注入，backward-compatible。
- `analytics-summary` 額外注入 `meta.cache_state ∈ {warm, cold, stale}`。
- `/health` / `/health/deep`（2026-03-11）：additive `system_memory` + `async_workers` blocks，backward-compatible。

## Breaking Change Policy

Breaking changes（移除欄位、改變 error code、改變 URL）需走 deprecate-2-minors 流程：先標記 deprecated，保留一個 minor 版本，再移除。
