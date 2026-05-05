---
contract: api-error-format
summary: Standard error payload shape, safety rules, and reusable error code table.
owner: application-team
surface: api
schema-version: 1.1.0
last-changed: 2026-05-05
---

# API Error Format

> 來源：遷移自 `contract/api_development_contract.md` §2.4 / §3（2026-05-05）

## Standard Error Shape

所有 `4xx` / `5xx` 回應必須使用此結構，透過 `core/response.py` 的輔助函式產生，禁止手動 `jsonify`：

```json
{
  "success": false,
  "error": {
    "code": "<ERROR_CODE_STRING>",
    "message": "<User-friendly message>",
    "details": "<development-only technical details>"
  },
  "meta": {
    "timestamp": "<ISO 8601 UTC>",
    "app_version": "<string>"
  }
}
```

- `code`：供機器讀取的標準化錯誤碼（必須使用預定義常數）。
- `message`：對終端使用者友善、可直接顯示的錯誤訊息。
- `details`：僅在 development mode 提供技術細節；production 下必須省略或置空。

## 標準錯誤碼 (Standard Error Codes)

| code | HTTP status | user-facing message | retryable | convenience function |
|---|---:|---|---:|---|
| `VALIDATION_ERROR` | 400 | 請求參數不正確 | no | `validation_error()` |
| `NOT_FOUND` | 404 | 找不到指定資源 | no | `not_found_error()` |
| `FORBIDDEN` | 403 | 無存取權限 | no | — |
| `UNAUTHORIZED` | 401 | 請先登入 | no | — |
| `DB_QUERY_ERROR` | 500 | 資料查詢失敗，請稍後再試 | yes | — |
| `SERVICE_UNAVAILABLE` | 503 | 服務暫時不可用，請稍後再試 | yes | — |
| `CACHE_EXPIRED` | 410 | 查詢快取已過期，請重新查詢 | yes (client re-triggers) | — |
| `INTERNAL_ERROR` | 500 | 系統發生錯誤，請聯絡管理員 | no | `internal_error()` |
| `QUERY_NOT_READY` | 409 | 查詢結果尚未就緒 | yes | — |
| `JOB_ALREADY_TERMINAL` | 409 | 工作已完成或失敗，無法再操作 | no | — |
| `RATE_LIMIT_EXCEEDED` | 429 | 請求過於頻繁，請稍後再試 | yes | — |

## Safety Rules

1. `details` 欄位僅在 `FLASK_DEBUG=1` 或 `FLASK_ENV=development` 時填入技術細節。
2. 新增錯誤碼需更新 `core/response.py` 預定義常數並更新此清單。
3. 優先使用便捷函式（`validation_error()`、`not_found_error()`、`internal_error()`），不要直接呼叫 `error_response()`。

## Special Cases

- **410 Cache Expired（Type A）：** view miss → 410 `CACHE_EXPIRED` → client 同步重觸發查詢。適用：hold-history、resource-history。
- **202 Async Job：** spool miss + RQ available → 202 `{async: true, job_id, status_url, ...}`。適用：reject-history、yield-alert、production-history、trace、material-trace。
- **503 DB Unavailable：** DB 連線失敗時回傳 503 `SERVICE_UNAVAILABLE` with `detail: "database_unavailable"`。
