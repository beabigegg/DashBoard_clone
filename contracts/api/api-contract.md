---
contract: api
summary: API behavior, compatibility rules, and endpoint contract requirements.
owner: application-team
surface: api
schema-version: 1.9.0
last-changed: 2026-05-20
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
| POST | /api/auth/login | public | JSON {username,password} | success_response | 400/401/429 | route tests |
| POST | /api/auth/logout | public | — | success_response | — | route tests |
| GET | /api/auth/me | public | — | success_response | — | route tests |
| PATCH | /api/auth/heartbeat | required | — | success_response | 401 | route tests |
| GET | /health | none | — | health-payload | — | smoke tests |
| GET | /health/deep | none | — | health-payload | — | smoke tests |
| GET | /api/job/<job_id> | required | ?prefix= | success_response | 400/404 | route tests |
| POST | /api/job/<job_id>/abandon | required | JSON body | success_response | 403/404/409 | route tests |
| GET | /api/spool/<namespace>/<query_id>.parquet | required | — | parquet-binary | 404/410 | route tests |
| GET | /api/wip/overview/summary | required | query params | success_response | 400/500 | route tests |
| GET | /api/wip/overview/matrix | required | query params | success_response | 400/500 | route tests |
| GET | /api/wip/overview/hold | required | query params | success_response | 400/500 | route tests |
| GET | /api/wip/detail/<workcenter> | required | query params | success_response | 400/500 | route tests |
| GET | /api/wip/lot/<lotid> | required | — | success_response | 404/500 | route tests |
| GET | /api/wip/meta/workcenters | required | — | success_response | 500 | route tests |
| GET | /api/wip/meta/packages | required | — | success_response | 500 | route tests |
| GET | /api/wip/meta/filter-options | required | query params | success_response | 500 | route tests |
| GET | /api/wip/meta/search | required | ?q= | success_response | 400/500 | route tests |
| GET | /api/hold-overview/summary | required | query params | success_response | 400/500 | route tests |
| GET | /api/hold-overview/matrix | required | query params | success_response | 400/500 | route tests |
| GET | /api/hold-overview/treemap | required | query params | success_response | 400/500 | route tests |
| GET | /api/hold-overview/lots | required | query params | success_response | 400/500 | route tests |
| GET | /api/wip/hold-detail/summary | required | query params | success_response | 400/500 | route tests |
| GET | /api/wip/hold-detail/distribution | required | query params | success_response | 400/500 | route tests |
| GET | /api/wip/hold-detail/lots | required | query params | success_response | 400/500 | route tests |
| GET | /api/hold-history/config | required | — | success_response | 500 | route tests |
| POST | /api/hold-history/query | required | JSON body | success_response | 400/410/500 | route tests |
| POST | /api/hold-history/today-snapshot | required | JSON body | success_response | 400/503 | e2e tests |
| GET | /api/hold-history/view | required | ?query_id= | success_response | 400/410 | route tests |
| GET | /api/qc-gate/summary | required | — | success_response | 500 | route tests |
| GET | /api/resource/by_status | required | — | success_response | 500 | route tests |
| GET | /api/resource/by_workcenter | required | — | success_response | 500 | route tests |
| GET | /api/resource/workcenter_status_matrix | required | — | success_response | 500 | route tests |
| POST | /api/resource/detail | required | JSON body | success_response | 400/500 | route tests |
| GET | /api/resource/filter_options | required | — | success_response | 500 | route tests |
| GET | /api/resource/status_values | required | — | success_response | 500 | route tests |
| GET | /api/resource/status | required | query params | success_response | 400/500 | route tests |
| GET | /api/resource/status/options | required | — | success_response | 500 | route tests |
| GET | /api/resource/status/summary | required | query params | success_response | 400/500 | route tests |
| GET | /api/resource/status/matrix | required | query params | success_response | 400/500 | route tests |
| GET | /api/resource/history/options | required | — | success_response | 500 | route tests |
| POST | /api/resource/history/query | required | JSON body | success_response | 400/410/500 | route tests |
| GET | /api/resource/history/view | required | ?query_id= | success_response | 400/410 | route tests |
| GET | /api/resource/history/export | required | query params | csv-stream | 400/410 | e2e tests |
| GET | /api/resource/history/query/progress | required | ?query_id=<uuid> | success_response | 400/404 | route tests |
| GET | /api/reject-history/options | required | — | success_response | 500 | route tests |
| GET | /api/reject-history/summary | required | ?query_id= | success_response | 400/410 | route tests |
| GET | /api/reject-history/trend | required | ?query_id= | success_response | 400/410 | route tests |
| GET | /api/reject-history/reason-pareto | required | ?query_id= | success_response | 400/410 | route tests |
| POST | /api/reject-history/batch-pareto | required | JSON body | success_response | 400/410 | route tests |
| GET | /api/reject-history/list | required | ?query_id=&page= | success_response | 400/410 | route tests |
| GET | /api/reject-history/export | required | ?query_id= | csv-stream | 400/410 | e2e tests |
| GET | /api/reject-history/export-cached | required | ?query_id= | csv-stream | 400/410 | e2e tests |
| GET | /api/reject-history/analytics | required | ?query_id= | success_response | 400/410 | route tests |
| POST | /api/reject-history/query | required | JSON body | success_response | 202/400/500 | route tests |
| GET | /api/reject-history/count | required | ?query_id= | success_response | 400/410 | route tests |
| GET | /api/reject-history/job/<job_id> | required | — | success_response | 404 | route tests |
| GET | /api/reject-history/view | required | ?query_id= | success_response | 400/410 | route tests |
| POST | /api/yield-alert/query | required | JSON body | success_response | 202/400/500 | route tests |
| GET | /api/yield-alert/job/<job_id> | required | — | success_response | 404 | route tests |
| GET | /api/yield-alert/analyze | required | ?query_id= | success_response | 400/410 | route tests |
| GET | /api/yield-alert/view | required | ?query_id= | success_response | 400/410 | route tests |
| GET | /api/yield-alert/summary | required | ?query_id= | success_response | 400/410 | route tests |
| GET | /api/yield-alert/trend | required | ?query_id= | success_response | 400/410 | route tests |
| GET | /api/yield-alert/alerts | required | ?query_id= | success_response | 400/410 | route tests |
| GET | /api/yield-alert/reason-detail | required | ?query_id=&reason= | success_response | 400/410 | route tests |
| GET | /api/yield-alert/drilldown-context | required | ?query_id= | success_response | 400/410 | route tests |
| GET | /api/yield-alert/filter-options | required | — | success_response | 500 | route tests |
| GET | /api/yield-alert/cross-filter-options | required | ?query_id=&lines[]=... | success_response | 400/410 | route tests |
| GET | /api/production-history/type-options | required | — | success_response | 500 | route tests |
| GET | /api/production-history/filter-options | required | ?selected=<json> | success_response | 400/404/500 | route tests |
| GET | /api/production-history/options | required | — | success_response | 503 | route tests |
| POST | /api/production-history/query | required | JSON body | success_response | 202/400/503 | route tests |
| GET | /api/production-history/job/<job_id> | required | — | success_response | 404 | route tests |
| POST | /api/production-history/page | required | JSON body | success_response | 400/410 | route tests |
| POST | /api/production-history/matrix | required | JSON body | success_response | 400/410 | route tests |
| GET | /api/production-history/count | required | ?query_id= | success_response | 400/410 | route tests |
| GET | /api/production-history/export | required | query params | csv-stream | 400/410 | e2e tests |
| POST | /api/material-trace/query | required | JSON body | success_response | 202/400/503 | route tests |
| GET | /api/material-trace/job/<job_id> | required | — | success_response | 404 | route tests |
| POST | /api/material-trace/export | required | JSON {query_hash} | csv-stream | 400/409 | e2e tests |
| GET | /api/material-trace/filter-options | required | — | success_response | 500 | route tests |
| POST | /api/trace/seed-resolve | required | JSON body | success_response | 400/500 | route tests |
| POST | /api/trace/lineage | required | JSON body | success_response | 202/400/500 | route tests |
| GET | /api/trace/lineage/job/<job_id> | required | — | success_response | 404 | route tests |
| GET | /api/trace/lineage/job/<job_id>/result | required | — | success_response | 404/410 | route tests |
| POST | /api/trace/events | required | JSON body | success_response | 400/500 | route tests |
| GET | /api/trace/job/<job_id> | required | — | success_response | 404 | route tests |
| GET | /api/trace/job/<job_id>/result | required | — | success_response | 404/410 | route tests |
| GET | /api/trace/job/<job_id>/stream | required | — | ndjson-stream | 404 | e2e tests |
| GET | /api/mid-section-defect/station-options | required | — | success_response | 500 | route tests |
| GET | /api/mid-section-defect/analysis | required | query params | success_response | 400/500 | route tests |
| GET | /api/mid-section-defect/analysis/detail | required | query params | success_response | 400/500 | route tests |
| GET | /api/mid-section-defect/loss-reasons | required | — | success_response | 500 | route tests |
| GET | /api/mid-section-defect/export | required | query params | csv-stream | 400/500 | e2e tests |
| GET | /api/analytics/anomaly-summary | required | — | success_response+cache_state | 503 | route tests |
| GET | /api/analytics/yield-anomalies | required | — | success_response | 503 | route tests |
| GET | /api/analytics/reject-spikes | required | — | success_response | 503 | route tests |
| GET | /api/analytics/hold-outliers | required | — | success_response | 503 | route tests |
| GET | /api/analytics/equipment-deviation | required | — | success_response | 503 | route tests |
| GET | /api/analytics/yield-anomalies/drilldown | required | ?query_id= | success_response | 400/410/503 | route tests |
| GET | /api/analytics/reject-spikes/drilldown | required | ?query_id= | success_response | 400/410/503 | route tests |
| GET | /api/analytics/hold-outliers/drilldown | required | ?query_id= | success_response | 400/410/503 | route tests |
| GET | /api/analytics/equipment-deviation/drilldown | required | ?query_id= | success_response | 400/410/503 | route tests |
| POST | /api/query-tool/resolve | required | JSON body | success_response | 400/500 | route tests |
| GET | /api/query-tool/lot-history | required | ?lot_id= | success_response | 400/500 | route tests |
| GET | /api/query-tool/adjacent-lots | required | ?lot_id= | success_response | 400/500 | route tests |
| GET | /api/query-tool/lot-associations | required | ?lot_id= | success_response | 400/500 | route tests |
| POST | /api/query-tool/equipment-period | required | JSON body | success_response | 400/500 | route tests |
| GET | /api/query-tool/equipment-list | required | — | success_response | 500 | route tests |
| GET | /api/query-tool/workcenter-groups | required | — | success_response | 500 | route tests |
| POST | /api/query-tool/lot-equipment-lookup | required | JSON body | success_response | 400/500 | route tests |
| GET | /api/query-tool/equipment-recent-jobs/<equipment_id> | required | — | success_response | 404/500 | route tests |
| POST | /api/query-tool/export-csv | required | JSON body | csv-stream | 400/500 | e2e tests |
| GET | /api/job-query/resources | required | — | success_response | 500 | route tests |
| POST | /api/job-query/jobs | required | JSON body | success_response | 400/500 | route tests |
| GET | /api/job-query/txn/<job_id> | required | — | success_response | 404/500 | route tests |
| POST | /api/job-query/export | required | JSON body | csv-stream | 400/500 | e2e tests |
| POST | /api/dashboard/kpi | required | JSON body | success_response | 400/500 | route tests |
| POST | /api/dashboard/workcenter_cards | required | JSON body | success_response | 400/500 | route tests |
| POST | /api/dashboard/detail | required | JSON body | success_response | 400/500 | route tests |
| POST | /api/dashboard/ou_trend | required | JSON body | success_response | 400/500 | route tests |
| POST | /api/dashboard/utilization_heatmap | required | JSON body | success_response | 400/500 | route tests |
| POST | /api/ai/query | required | JSON body | success_response | 400/500 | route tests |
| GET | /admin/api/system-status | admin | — | success_response | 403/500 | route tests |
| GET | /admin/api/metrics | admin | — | success_response | 403/500 | route tests |
| GET | /admin/api/logs | admin | query params | success_response | 403/500 | route tests |
| DELETE | /admin/api/logs/cleanup | admin | — | success_response | 403/500 | route tests |
| DELETE | /admin/api/log-files/cleanup | admin | — | success_response | 403/500 | route tests |
| GET | /admin/api/performance-detail | admin | query params | success_response | 403/500 | route tests |
| GET | /admin/api/performance-history | admin | query params | success_response | 403/500 | route tests |
| DELETE | /admin/api/performance-history/purge | admin | — | success_response | 403/500 | route tests |
| GET | /admin/api/storage-info | admin | — | success_response | 403/500 | route tests |
| POST | /admin/api/worker/restart | admin | — | success_response | 403/500 | route tests |
| GET | /admin/api/worker/status | admin | — | success_response | 403/500 | route tests |
| GET | /admin/api/user-usage-kpi | admin | ?start_date=&end_date=&department= | success_response | 400/403 | route tests |
| GET | /admin/api/pages | admin | — | success_response | 403/500 | route tests |
| GET | /admin/api/drawers | admin | — | success_response | 403/500 | route tests |
| POST | /admin/api/drawers | admin | JSON body | success_response | 400/403 | route tests |
| GET | /admin/api/drawers/<drawer_id> | admin | — | success_response | 403/404 | route tests |
| PUT | /admin/api/drawers/<drawer_id> | admin | JSON body | success_response | 400/403/404 | route tests |
| DELETE | /admin/api/drawers/<drawer_id> | admin | — | success_response | 403/404 | route tests |
| POST | /admin/api/analytics/recalculate | admin | — | success_response | 403/500 | route tests |

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
- **resource-history progress endpoint（2026-05-13，resource-history-perf）**：新增 `GET /api/resource/history/query/progress?query_id=<uuid>`；auth required；response shape: `{ query_id, total_chunks, completed_chunks, percent, status }`；`status` 為 closed enum `running | done | error`；400 on missing `query_id`，404 on unknown `query_id`；additive，不影響既有端點。
- **Production-History first-tier cache filters（2026-05-14，prod-history-first-tier-cache-filters）**：以下為 additive，backward-compatible：
  - 新增端點：`GET /api/production-history/filter-options?selected=<json>`；auth required；response `success_response`；errors 400/404/500。
  - `selected` 為 URL-encoded JSON：`{"pj_types":[],"packages":[],"bops":[],"pj_functions":[]}`；空物件或省略 → 回傳完整四欄 distinct 集合（empty-selection 場景，AC-1）。
  - Response payload：`data: {pj_types[], packages[], bops[], pj_functions[]}` + `meta: {updated_at, schema_version: 2}`。
  - 主查詢端點 `POST /api/production-history/query` 新增六個可選 JSON body 欄位（全部 additive，缺省時與舊行為一致）：
    - `pj_packages[]`（string 陣列，cached MultiSelect，plain `IN`）
    - `pj_bops[]`（string 陣列，cached MultiSelect，plain `IN`）
    - `pj_functions[]`（string 陣列，cached MultiSelect，plain `IN`）
    - `mfg_orders[]`（string 陣列，支援 `*` 萬用字元，依 PHF-02/PHF-03 規則 bind `LIKE ESCAPE '\'`）
    - `lot_ids[]`（string 陣列，支援 `*` 萬用字元；上游既有 `IN` 行為升級為 wildcard-aware）
    - `wafer_lots[]`（string 陣列，支援 `*` 萬用字元，新欄位）
  - 萬用字元語法見 business-rules.md PHF-02；server-side validation 拒絕 SQL meta-char（PHF-06），最多 100 patterns/field。
  - Type-only flow 不變（其他欄位皆 optional，省略時即既有行為）。
- **Production-History query-mode tabs（2026-05-14，prod-history-query-mode-tabs）**：以下為 additive，backward-compatible：
  - `POST /api/production-history/query` 的 `start_date` / `end_date` 由「無條件必填」放寬為「條件必填」：
    - **Classification mode**（request body 不含任何 identifier wildcard token — `mfg_orders` / `lot_ids` / `wafer_lots` 皆空或缺省）：`start_date` / `end_date` 仍為必填，缺少時 → 400 `VALIDATION_ERROR`（行為與舊版完全一致）。
    - **Identifier mode**（request body 含至少一個 `mfg_orders` / `lot_ids` / `wafer_lots` token）：`start_date` / `end_date` 為可選；兩者皆缺省時執行 wide / all-time 查詢，不再回傳 dates-required 錯誤。
  - 當 identifier token 存在「且」日期亦有提供時，日期上限規則（730d，VAL-03 / SYS-04）仍適用。
  - 既有 callers（classification 流程、現有測試）一律持續送出 `start_date` / `end_date`，行為不變；此變更不影響 first-tier cache filter 機制、wildcard 文法、second-tier 過濾或 matrix/detail 渲染。
  - Per-mode 驗證語意見 business-rules.md PHF-07 / PHF-08。
- **WIP new filter params（2026-05-13，wip-hold-drilldown-filters）**：以下四個端點新增三個可選查詢參數，全部為 additive，不影響既有呼叫方：
  - 端點：`GET/POST /api/wip/detail/<workcenter>`、`GET/POST /api/wip/overview/summary`、`GET/POST /api/wip/overview/matrix`、`GET/POST /api/wip/meta/filter-options`
  - 新增參數：
    - `workflow`（string，optional）：WORKFLOWNAME 精確比對過濾
    - `bop`（string，optional）：BOP 精確比對過濾
    - `pj_function`（string，optional）：PJ_FUNCTION 精確比對過濾
  - `GET/POST /api/wip/detail/<workcenter>` lot 列新增 `pjType` 欄位（來源：DB `PJ_TYPE` 欄）；null 值以 `null` 回傳。
  - `GET/POST /api/wip/meta/filter-options` response 新增三個 string array：`workflows`、`bops`、`pjFunctions`，與既有 `workorders` / `lotids` / `packages` / `types` / `firstnames` / `waferdescs` 並列。
- **Production-History detail partial-trackout aggregation (2026-05-15, prod-history-detail-partial-merge)**：以下為 additive，backward-compatible：
  - `POST /api/production-history/page` response：`data.rows` 每筆 row 新增 `partial_count: integer (≥ 1)`。`1` 表示未合併列；`≥ 2` 表示這列聚合了多筆 partial track-out（同一上機 session，4 鍵 `lot_id + spec + equipment_id + trackin_time`）。當 `partial_count ≥ 2` 時 `trackin_qty` 為原始上機量（`MAX(...)`，因 MES `TRACKINQTY` 隨 partial 遞減），`trackout_time = MAX(...)`，`trackout_qty = SUM(...)`。Additive；既有忽略未知欄位的 consumer 不受影響。
  - `GET /api/production-history/export` CSV：在原最後一欄 `TrackOutQty` 之後新增一欄 `PartialCount`。完整欄位順序：`LotID, Type, Package, BOP, Function, WorkOrder, WaferLot, WorkCenter, Spec, EquipmentID, EquipmentName, TrackInTime, TrackOutTime, TrackInQty, TrackOutQty, PartialCount`。以位置解析 CSV 的 consumer 需處理新尾欄；視為 additive（沿用 Breaking Change Policy）。
  - `pagination.total_rows`（`POST /api/production-history/page`）語意更新：反映聚合後的列數，而非 raw spool 列數。當查詢無 partial trackout 時兩者相同；當有合併群組時 `total_rows` 小於原 LOTWIPHISTORY 列數。
  - 三條後端路徑（DuckDB SQL 主路徑、pandas fallback、CSV 匯出）一致套用相同聚合邏輯。
  - 嚴格守門：群組內非鍵欄位若有差異則該群組退回 raw rows（不合併），對 API consumer 透明 — 無新錯誤碼。詳見 business-rules.md PH-06 / PH-07。
- **Admin dashboard fixes（2026-05-19，fix-admin-dashboard）**：以下為 additive，backward-compatible：
  - `GET /admin/api/performance-detail` `data.redis` 子物件新增四個 key：`evicted_keys`（integer），`expired_keys`（integer），`mem_fragmentation_ratio`（float），`slowlog`（array of top-5 entries：`{id, duration_us, command}`）。Redis 不可達時整個 `data.redis` 維持 `null` 或 `{"error": "..."}` 行為不變。
  - `GET /admin/api/performance-detail` 新增頂層 `data.duckdb` 子物件：`{temp_dir_bytes: integer|null, memory_limit_state: string|null}`。DuckDB telemetry 不可用時 `data.duckdb` 為 `null`。
  - `GET /admin/api/logs` 查詢範圍從「僅未同步記錄（synced=0）」擴大為「全部記錄（含已同步）」；pagination 修正為在 merge sort 後正確套用 offset/limit；response schema 不變。
  - 無端點新增/刪除/重新命名；無現有 key 移除或更名；所有改動為 additive。
- **Query-Tool partial-trackout aggregation (2026-05-15, query-tool-partial-trackout)**：以下為 additive，backward-compatible：
  - `GET /api/query-tool/lot-history` 與 `POST /api/query-tool/equipment-period`（`query_type=lots`）response rows 新增 `partial_count: integer (≥ 1)`。`TRACKINQTY` 改為 `MAX(TRACKINQTY)`（原始上機量，因 MES `TRACKINQTY` 隨 partial 遞減）；`TRACKOUTQTY` 改為 `SUM(TRACKOUTQTY)`（累計下機量）；`TRACKOUTTIMESTAMP` 改為 `MAX(TRACKOUTTIMESTAMP)`。舊行為為 `ROW_NUMBER() ... WHERE rn=1` 取最後一筆 partial —— 為靜默的數據準確性 bug。
  - `GET /api/query-tool/adjacent-lots` response rows 同樣新增 `partial_count: integer (≥ 1)`，使用 3-tuple `(CONTAINERID, EQUIPMENTID, TRACKINTIMESTAMP)` 聚合語意。
  - `partial_count` 為 additive 新欄位；既有忽略未知欄位的 consumer 不受影響。
  - 無端點移除、無欄位移除、無錯誤碼變更。
  - 嚴格守門：群組內非鍵欄位差異 → raw rows 各帶 `partial_count = 1`，對 API consumer 透明。詳見 business-rules.md QT-05 / QT-06。
  - `POST /api/query-tool/export-csv`（`export_type=lot_history` 與 `export_type=equipment_lots`）CSV 新增 `partial_count` 為傳遞欄位；以位置解析 CSV 的 consumer 需處理新尾欄。
- **Query-Tool equipment-rejects detail rewrite (2026-05-18, `equipment-rejects-by-lots`)**: `POST /api/query-tool/equipment-period` (`query_type='rejects'`) and `POST /api/query-tool/export-csv` (`export_type='equipment_rejects'`) response shape changed from aggregate (EQUIPMENTNAME, LOSSREASONNAME, TOTAL_REJECT_QTY, TOTAL_DEFECT_QTY, AFFECTED_LOT_COUNT) to per-reject-event detail rows (see data-shape-contract.md §3.7). Data source changed from LOTREJECTHISTORY filtered by EQUIPMENTNAME to LOTWIPHISTORY→LOTREJECTHISTORY via CONTAINERID (fixes cross-station reject omission). Service parameter renamed `equipment_names → equipment_ids`. Hard cutover — both EquipmentView and LotEquipmentView consumers ship in the same PR. Deprecate-2-minors policy bypassed because all consumers are in the same monorepo and shipped atomically.

- **Material-Consumption endpoints（2026-05-20，material-part-consumption）**：以下為 additive，新頁面，不影響既有端點：
  - 新增 7 個端點：`GET /api/material-consumption/filter-options` → `{workcenter_groups, primary_categories, pj_types}`；`POST /api/material-consumption/query`（summary sync，body: `{material_parts[1..20], start_date, end_date, granularity: week|month|quarter, workcenter_groups?, primary_categories?, pj_types?}`，response: `{query_id, kpi: {total_consumed, total_required, efficiency_pct, lot_count, workorder_count}, trend[], type_breakdown[]}`）；`GET /api/material-consumption/view?query_id=X&granularity=Y`（DuckDB regroup，no Oracle，410 on spool miss）；`POST /api/material-consumption/detail`（sync 200 when rows ≤ SYNC_ROW_LIMIT，else 202 async；response: `{query_id, rows[], pagination: {page, total_pages, total_rows, per_page}}`）；`GET /api/material-consumption/detail/page?query_id=X&page=N`；`GET /api/material-consumption/detail/job/<job_id>` → `{status: pending|running|done|failed, query_id?}`；`POST /api/material-consumption/export`（csv-stream，text/csv，DuckDB chunked，no full-memory load）。
  - Summary query always synchronous. Detail query sync ≤ `SYNC_ROW_LIMIT` (env default 30000); async Type B (RQ queue `material-consumption`) for larger sets.
  - `GET /view` summary spool cache key EXCLUDES granularity — one spool serves all three granularity views; DuckDB re-groups in milliseconds.
  - `material_parts` cap: 20 values; `*` wildcard → `LIKE %`; SQL meta-chars → 400 VALIDATION_ERROR (business-rules.md MC-02).
  - Parquet spool schema is breaking-change surface: column rename/add/remove → `rm -f tmp/query_spool/material_consumption/*.parquet` on deploy and rollback.
  - Consumers: `frontend/src/material-consumption/` (new, no existing consumer); Admin Dashboard `rq_monitor_service` updated with new queue name (additive).

## Breaking Change Policy

Breaking changes（移除欄位、改變 error code、改變 URL）需走 deprecate-2-minors 流程：先標記 deprecated，保留一個 minor 版本，再移除。

## CHANGELOG

## [api 1.9.0]
- material-part-consumption (2026-05-20): Added 7 endpoints under `/api/material-consumption` (filter-options, query, view, detail, detail/page, detail/job, export). New additive surface; no existing endpoints changed.
