## Why

Released 頁面目前直接套用到生產環境，且部署型態為無反向代理的單層對外服務；現況在 API 輸入驗證、流量防護、設定安全預設、與錯誤處理上仍有可導致 500、資源耗盡或安全邊界被繞過的風險。需要以一次性治理方式補齊基線，並建立可重複執行的無回歸驗證，避免修正後再次退化。

## What Changes

- 統一 Released 頁面相關高成本 API 的輸入驗證與錯誤語義：非 JSON 或格式錯誤請求回覆 4xx，不再落入 500。
- 為 query-tool 與 resource 等批次/明細查詢加入明確上限（批量 ID、limit、payload size）與拒絕策略，降低 DoS 與慢查風險。
- 強化 rate-limit 客戶端識別信任邊界：在無 trusted proxy 情境下不可直接信任 `X-Forwarded-For`。
- 對生產安全設定採 fail-safe 預設：`api_public`、`FLASK_ENV`、`SECRET_KEY`、Redis URL log masking 等。
- 收斂前端可注入風險（如 inline handler 字串插值）與 CSP 風險設定，降低 XSS 面。
- 建立 Released 頁面專屬無回歸驗證矩陣（正向、負向、壓力邊界、契約），納入 CI gate。

## Capabilities

### New Capabilities
- `released-pages-production-hardening`: 定義 Released 頁面在生產環境的輸入驗證、資源保護、信任邊界、安全預設與回歸防線要求。

### Modified Capabilities
- None.

## Impact

- Affected code:
  - `src/mes_dashboard/routes/job_query_routes.py`
  - `src/mes_dashboard/routes/query_tool_routes.py`
  - `src/mes_dashboard/routes/resource_routes.py`
  - `src/mes_dashboard/routes/hold_routes.py`
  - `src/mes_dashboard/routes/wip_routes.py`
  - `src/mes_dashboard/core/rate_limit.py`
  - `src/mes_dashboard/core/redis_client.py`
  - `src/mes_dashboard/config/settings.py`
  - `src/mes_dashboard/app.py`
  - `frontend/src/job-query/main.js`
  - `data/page_status.json`
- APIs/routes: Released route 對應 API（包含 `/api/query-tool/*`, `/api/job-query/*`, `/api/resource/*` 等）會新增/明確化 4xx 與 429 邊界行為。
- Tests/quality gates: 新增與擴充 Released 頁面 API 的負向驗證、限流、上限邊界與模板整合回歸測試；CI 需納入通過條件。
