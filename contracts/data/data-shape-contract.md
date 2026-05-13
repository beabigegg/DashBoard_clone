---
contract: data
summary: Data schema, invalid-data handling, and row-level compatibility rules.
owner: application-team
surface: data
schema-version: 1.0.2
last-changed: 2026-05-13
breaking-change-policy: deprecate-2-minors
---

# Data Shape Contract — MES Dashboard

> 來源：掃描 `src/mes_dashboard/core/response.py`、`tests/test_api_contract.py`、`tests/test_field_contracts.py`（2026-05-05）

---

## 1. API Envelope Shapes

### 1.1 Success Envelope

```json
{
  "success": true,
  "data": "<payload>",
  "meta": {
    "timestamp": "<ISO 8601 local>",
    "app_version": "<string>"
  }
}
```

- `meta.app_version` 由 `success_response()` 自動注入（`APP_VERSION` env 或 package metadata）。
- 額外 meta 欄位（`cache_state`、`pagination`、`cached`）為 additive，不算 breaking change。

### 1.2 Error Envelope

```json
{
  "success": false,
  "error": {
    "code": "<ERROR_CODE>",
    "message": "<user-facing string>",
    "details": "<dev-only string | omitted in production>"
  },
  "meta": {
    "timestamp": "<ISO 8601 local>",
    "app_version": "<string>"
  }
}
```

### 1.3 Async Job 202 Response

```json
{
  "success": true,
  "data": {
    "async": true,
    "job_id": "<uuid string>",
    "status_url": "/api/job/<job_id>?prefix=<namespace>",
    "query_id": "<string | optional>",
    "dataset_id": "<string | optional>"
  },
  "meta": { "timestamp": "...", "app_version": "..." }
}
```

### 1.4 Async Job Status Response

```json
{
  "success": true,
  "data": {
    "status": "queued | started | finished | failed | abandoned",
    "job_id": "<string>",
    "result": "<payload | null>",
    "error": "<string | null>"
  },
  "meta": { "timestamp": "...", "app_version": "..." }
}
```

---

## 2. Common Query Result Shapes

### 2.1 Paginated List

```json
{
  "success": true,
  "data": {
    "query_id": "<string>",
    "list": [ "<row objects>" ],
    "pagination": {
      "page": 1,
      "per_page": 50,
      "total_count": 1234,
      "total_pages": 25
    }
  },
  "meta": { "timestamp": "...", "app_version": "..." }
}
```

### 2.2 Summary + Detail Pattern（resource-history、hold-history）

```json
{
  "success": true,
  "data": {
    "query_id": "<string>",
    "summary": { "<module-specific KPIs>" },
    "detail": [ "<row objects>" ]
  },
  "meta": { "timestamp": "...", "app_version": "..." }
}
```

### 2.3 Hold-History Today Snapshot

```json
{
  "success": true,
  "data": {
    "query_id": "<string>",
    "summary": {
      "onHoldTotalCount": 0,
      "onHoldTotalQty": 0,
      "todayNewQty": 0,
      "todayReleaseQty": 0,
      "todayFutureHoldQty": 0,
      "onHoldAvgHours": 0.0,
      "onHoldMaxHours": 0.0
    },
    "reason_pareto": [ "<pareto rows>" ],
    "duration": {
      "items": [
        { "range": "<string>", "count": 0, "qty": 0, "pct": 0.0 }
      ],
      "avgReleasedHours": 0.0,
      "avgOnHoldHours": 0.0,
      "maxReleasedHours": 0.0,
      "maxOnHoldHours": 0.0
    },
    "list": [ "<lot rows>" ]
  }
}
```

### 2.5 WIP Filter-Options Response（`/api/wip/meta/filter-options`）

```json
{
  "success": true,
  "data": {
    "workorders":   ["<string>"],
    "lotids":       ["<string>"],
    "packages":     ["<string>"],
    "types":        ["<string>"],
    "firstnames":   ["<string>"],
    "waferdescs":   ["<string>"],
    "workflows":    ["<string>"],
    "bops":         ["<string>"],
    "pjFunctions":  ["<string>"]
  },
  "meta": { "timestamp": "...", "app_version": "..." }
}
```

- `workflows`、`bops`、`pjFunctions` 為 additive 新增欄位（wip-hold-drilldown-filters）。
- 各欄位均為 distinct 排序字串陣列；若無符合值則回傳 `[]`。
- 支援 cross-filter 語意：選取某過濾器時，其他欄位選項自動縮減至對應可選值。
- 接受可選查詢參數 `workflow`、`bop`、`pj_function` 以在已選取過濾器後縮減選項。

### 2.6 Resource-History Batch Query Progress（`GET /api/resource/history/query/progress`）

Response shape for an active or completed batch query (HTTP 200):

```json
{
  "success": true,
  "data": {
    "query_id": "<uuid string>",
    "total_chunks": "<integer>",
    "completed_chunks": "<integer>",
    "percent": "<float 0.0–100.0>",
    "status": "<running | done | error>"
  },
  "meta": { "timestamp": "...", "app_version": "..." }
}
```

Constraints:
- All five `data` fields are required; the endpoint MUST NOT omit any of them in a 200 response.
- `status` is a closed enum: `running | done | error` — any other value is invalid.
- `percent` is `float`, range `[0.0, 100.0]`.
- 400 and 404 responses follow the standard error envelope (Section 1.2).
- This shape is wholly separate from the query result shape (Section 2.2); do not conflate.
- Added by change `resource-history-perf`.

### 2.4 Truncated Payload（memory pressure guard）

Large payloads that hit the memory/row limit include:

```json
{
  "_meta": {
    "truncated": true,
    "total_before_limit": 50000,
    "limit_applied": 10000
  }
}
```

---

## 3. Required Columns（Common Row Types）

### 3.1 Lot Row（WIP / Hold）

| column | type | nullable | notes |
|---|---|---:|---|
| lot_id | string | no | primary identifier |
| product | string | yes | may be null for some lot types |
| qty | integer | no | — |
| location | string | yes | workcenter or step name |

#### 3.1.1 WIP Detail Lot Row（`/api/wip/detail/<workcenter>` lots array）

| column | type | nullable | notes |
|---|---|---:|---|
| lotId | string | no | LOTID |
| equipment | string | yes | EQUIPMENTS |
| wipStatus | string | yes | WIP_STATUS |
| holdReason | string | yes | HOLDREASONNAME |
| qty | integer | no | QTY |
| package | string | yes | PACKAGE_LEF |
| spec | string | yes | SPECNAME |
| pjType | string | yes | PJ_TYPE；null renders as `-` in UI（additive, wip-hold-drilldown-filters）|

### 3.2 Duration Item

| column | type | nullable | notes |
|---|---|---:|---|
| range | string | no | e.g. "0-24h", "24-72h" |
| count | integer | no | lot count in this range |
| qty | integer | no | lot quantity sum |
| pct | float | no | percentage of total |

### 3.3 Pareto Row

| column | type | nullable | notes |
|---|---|---:|---|
| reason | string | no | hold/reject reason code |
| count | integer | no | occurrence count |
| qty | integer | no | quantity sum |
| pct | float | no | running cumulative % |

---

## 4. Invalid Data Behavior

| condition | expected behavior | error code / UI state | test |
|---|---|---|---|
| missing required column | service raises ValueError → 500 INTERNAL_ERROR | INTERNAL_ERROR | `tests/test_field_contracts.py` |
| wrong type (e.g. string qty) | type coercion or 400 VALIDATION_ERROR | VALIDATION_ERROR | `tests/test_field_contracts.py` |
| empty dataset | returns empty list `[]`; UI shows EmptyState | — | `frontend/tests/playwright/data-boundary/empty-result.spec.js` |
| over max row limit | truncated; adds `_meta.truncated=true` to payload | — | `tests/test_interactive_memory_guard.py` |
| unexpected enum value | 400 VALIDATION_ERROR | VALIDATION_ERROR | `tests/routes/test_fuzz_routes.py` |
| malicious input (SQL/XSS/100k) | 400 VALIDATION_ERROR (never 500) | VALIDATION_ERROR | `tests/routes/test_fuzz_routes.py` |
| DB unavailable | 503 SERVICE_UNAVAILABLE | SERVICE_UNAVAILABLE | `tests/test_degraded_responses.py` |
| Spool expired | 410 CACHE_EXPIRED or dataset_expired | CACHE_EXPIRED | resilience tests |
| Date range > 730 days | 400 VALIDATION_ERROR | VALIDATION_ERROR | route tests |

---

## 5. Export / Import Format

- **CSV export**：`Content-Type: text/csv; charset=utf-8`；`Content-Disposition: attachment; filename=<module>_<date>.csv`；header row 必須存在。
- **Parquet download**（spool）：`Content-Type: application/octet-stream`；binary Parquet format。
- **NDJSON stream**（trace）：`Content-Type: application/x-ndjson`；每行一個 JSON object。

---

## 6. Row Limit / Truncation Policy

| scope | limit | behavior |
|---|---|---|
| DuckDB spool paged query | `per_page` max 200 | hard cap per request |
| `/api/production-history/options` | memory guard | 503 on pressure |
| Trace events | `EVENT_FETCHER_MAX_TOTAL_ROWS=500000` | partial results if `EVENT_FETCHER_ALLOW_PARTIAL_RESULTS=true` |
| Material trace export | `MATERIAL_TRACE_MAX_RESULT_MB=256` | 413 if exceeded |
| Any JSON payload | internal soft cap | `_meta.truncated=true` added |

---

## 7. Breaking Change Policy

Removing a required column, changing a column type, or removing a key from the envelope requires:
1. Marking the field as `deprecated` for at least one minor version.
2. Adding a compatibility note to `contracts/api/api-contract.md`.
3. Updating related tests before removing the field.
