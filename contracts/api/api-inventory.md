---
contract: api-inventory
summary: Endpoint inventory categories and ownership map for non-standard API surfaces.
owner: application-team
surface: api
schema-version: 1.1.5
last-changed: 2026-05-18
---

# API Inventory

> 來源：遷移自 `contract/api_inventory.md`（2026-04-15 → 2026-05-05）  
> 治理範圍：`src/mes_dashboard/routes/*.py` + `app.py` 中的 `/api/*` bridge 端點  
> 排除：非 API 路由、前端 caller、static/dist 產物

---

## standard-json（必須使用 response helpers 與 envelope）

| File | Scope |
|---|---|
| `wip_routes.py` | All JSON API endpoints — `GET /api/wip/overview/summary`, `/matrix`, `/meta/filter-options`, `/overview/hold`；同時接受 `POST` JSON body（避免 URL 過長）。`/overview/summary`、`/overview/matrix`、`/detail/<workcenter>`、`/meta/filter-options` 接受新增可選參數 `workflow`、`bop`、`pj_function`（wip-hold-drilldown-filters）。`/detail/<workcenter>` lot 列新增 `pjType` 欄位。`/meta/filter-options` response 新增 `workflows`、`bops`、`pjFunctions` 陣列。 |
| `dashboard_routes.py` | All JSON API endpoints |
| `hold_routes.py` | All JSON API endpoints |
| `hold_overview_routes.py` | All JSON API endpoints — `/summary`, `/matrix`, `/treemap`, `/lots` 接受 `POST` JSON body；`reason` 可為 CSV string (GET) 或 JSON array (POST) |
| `hold_history_routes.py` | All JSON API endpoints — **Type A** (sync re-query on 410)；`duration` payload: `{ items: [{range, count, qty, pct}], avgReleasedHours, avgOnHoldHours, maxReleasedHours, maxOnHoldHours }`；trend day 含 `repeatQualityHoldQty`；**`POST /api/hold-history/today-snapshot`**: inputs `{ hold_type, record_type, reason, duration_range, page, per_page }`，response `{ query_id, summary: { onHoldTotalCount, onHoldTotalQty, todayNewQty, todayReleaseQty, todayFutureHoldQty, onHoldAvgHours, onHoldMaxHours }, reason_pareto, duration, list }`；cache `hold_today:*` TTL 60s；DB 不可用 → 503 `service_unavailable` |
| `reject_history_routes.py` | All JSON API endpoints — **Type B** (async 202 polling on 410)；含 `GET /api/reject-history/job/<job_id>`；`/batch-pareto` / `/view` 接受 `POST` JSON body |
| `resource_routes.py` | All JSON API endpoints |
| `resource_history_routes.py` | All JSON API endpoints — **Type A** (sync re-query on 410)；`POST /api/resource/history/query` 先查 canonical base spool（DuckDB filter）；response: `{query_id, summary, detail}`；**新增** `GET /api/resource/history/query/progress?query_id=<uuid>` — batch 查詢進度 side-channel；progress state 存於 Redis key `resource:history:progress:<query_id>`；400 on missing param，404 on unknown query_id；auth required（與其他端點相同 `login_required` guard）（resource-history-perf）。 |
| `yield_alert_routes.py` | All JSON API endpoints — **Type B** (async 202 polling)；`POST /api/yield-alert/query` 可回傳 202；RQ 不可用 fallback sync 200；`GET /api/yield-alert/cross-filter-options?query_id=...&lines[]=...&packages[]=...`，410 on spool expired |
| `production_history_routes.py` | All JSON API endpoints — `POST /api/production-history/query` 驗證 `pj_types`, `start_date`, `end_date`；缺少/無效 → 400 `VALIDATION_ERROR`；date range > 730d → 400；spool hit → 200，miss+RQ → 202；含 `POST /page`（DuckDB paged）、`/matrix`、`/options`；gated by `PROD_HISTORY_ENABLED`。**新增** `GET /api/production-history/filter-options?selected=<json>` — cross-filter cached options（4-tuple in-memory filter over `container_filter_cache`），auth required，400 on malformed `selected` JSON，404 on cache cold start failure，500 on Oracle build error；payload schema `{data: {pj_types, packages, bops, pj_functions}, meta: {updated_at, schema_version: 2}}`（prod-history-first-tier-cache-filters）。主查詢端點 `POST /api/production-history/query` 新增可選欄位 `pj_packages[]`、`pj_bops[]`、`pj_functions[]`（cached MultiSelect，plain `IN`）、`mfg_orders[]`、`lot_ids[]`、`wafer_lots[]`（多行 + `*` 萬用字元，依 PHF-02 規則 `LIKE ESCAPE '\'` bind）；全部 additive、缺省時保持 Type-only 行為。`start_date` / `end_date` 自 prod-history-query-mode-tabs 起為**條件必填**：classification mode（無 identifier token）仍必填；identifier mode（含 `mfg_orders` / `lot_ids` / `wafer_lots` token）可省略，省略時走 wide / all-time 查詢。 |
| `admin_routes.py` | `POST /api/admin/analytics/recalculate`（admin required）、`GET /admin/api/user-usage-kpi`（params: `start_date`, `end_date`, `department`） |
| `job_query_routes.py` | All JSON API endpoints |
| `qc_gate_routes.py` | All JSON API endpoints |
| `trace_routes.py` | All JSON API endpoints — `GET /api/trace/lineage/job/<job_id>` / `/result`；`POST /api/trace/lineage` 非同步 capable → 202；MSD events → `{spool_hit, trace_query_id, aggregation}`；`trace_query_id` 為 stable hash-based canonical query id |
| `mid_section_defect_routes.py` | All JSON API endpoints — **compatibility adapter**：`GET /api/mid-section-defect/analysis`；`/analysis/detail` / `/export` 接受可選 `trace_query_id` |
| `query_tool_routes.py` | All JSON API endpoints |
| `material_trace_routes.py` | JSON endpoints（CSV export 除外）— `POST /api/material-trace/query` spool 優先；miss → 202；RQ 不可用 → 503+Retry-After；`GET /api/material-trace/job/<job_id>`；`POST /api/material-trace/export` 需 `query_hash`，409 `QUERY_NOT_READY` if not ready |
| `analytics_routes.py` | `GET /api/analytics/yield-anomalies`, `/reject-spikes`, `/hold-outliers`, `/equipment-deviation`, `/anomaly-summary` 及各 `/drilldown`；gated by `ANALYTICS_ANOMALY_DETECTION_ENABLED`；`anomaly-summary` 注入 `meta.cache_state` |
| `user_auth_routes.py` | `POST /api/auth/login` (public, rate-limited 5/5min, JSON `{username, password}`)、`POST /api/auth/logout`、`GET /api/auth/me`（null if not logged in）、`PATCH /api/auth/heartbeat` (login_required) |
| `ai_routes.py` | `POST /api/ai/query` — NL query；`AI_MODE` 決定 pipeline；response: `{answer, chart_data, query_used, params_used, suggestions, sql_used, tool_trace, needs_clarification}`；gated by `AI_QUERY_ENABLED` |
| `job_routes.py` | `GET /api/job/<job_id>?prefix=<p>` — async 狀態；`POST /api/job/<job_id>/abandon` — idempotent，rate-limited 30/60s |

## Admin Page Routes（非 API）

| File | Routes | Notes |
|---|---|---|
| `admin_routes.py` | `/admin/performance`, `/admin/user-usage-kpi`, `/admin/dashboard` | Admin-auth SPA HTML；CSRF token 注入 HTML |

## health-exception（保持穩定頂層 payload；不強制 envelope）

| File | Endpoints | Reason |
|---|---|---|
| `health_routes.py` | `/health`, `/health/deep`, `/health/frontend-shell` | 被 monitoring 和 shell health UI 使用 |

> Additive (2026-03-11)：`/health` / `/health/deep` 加入 `system_memory` + `async_workers` blocks，backward-compatible。

## Internal-only（非 admin API，非 production deploy config）

| File | Endpoint | Gates | Notes |
|---|---|---|---|
| `internal_routes.py` | `GET /internal/metrics` | L1: `REGISTER_INTERNAL_METRICS=True`；L2: `INTERNAL_METRICS_ENABLED=1`；L3: loopback only | Soak test + nightly metrics probe 消費。7 stable keys: `{pool, duckdb, redis, spool, worker_rss, circuit_breaker, rq}`。Production MUST NOT expose。 |

## stream-download-exception（success 可為 non-JSON stream；JSON errors 仍用 envelope）

| File | Scope |
|---|---|
| `job_query_routes.py` | CSV export/stream |
| `material_trace_routes.py` | CSV trace export |
| `mid_section_defect_routes.py` | CSV export |
| `query_tool_routes.py` | CSV export/stream |
| `reject_history_routes.py` | CSV export |
| `resource_history_routes.py` | CSV export |
| `trace_routes.py` | NDJSON stream (`/api/trace/job/<job_id>/stream`) |
| `spool_routes.py` | `GET /api/spool/{namespace}/{query_id}.parquet` — Parquet binary download |
| `production_history_routes.py` | `GET /api/production-history/export` — full CSV stream |

## legacy-transition（暫時 bridge；retirement pending）

| File | Endpoints | Notes |
|---|---|---|
| `app.py` | `/api/query_table` | Legacy bridge |
| `app.py` | `/api/get_table_columns` | Legacy bridge |
| `app.py` | `/api/get_table_info` | Legacy bridge |
| `app.py` | `/api/portal/navigation` | Legacy bridge |

## Excluded

| File | Reason |
|---|---|
| `auth_routes.py` | Admin login/logout pages (`/admin/*`)，非 `/api/*` scope |

---

## Compatibility Notes

- **2026-05-14（prod-history-query-mode-tabs）：** `production_history_routes.py` 主查詢端點 `POST /api/production-history/query` 的 `start_date` / `end_date` 由無條件必填放寬為條件必填（classification mode 必填、identifier mode 可選）；無端點新增/刪除/重新命名；backward-compatible。Per-mode 驗證規則見 business-rules.md PHF-07 / PHF-08。
- **2026-05-14（prod-history-first-tier-cache-filters）：** `production_history_routes.py` 新增 `GET /api/production-history/filter-options` 端點（cross-filter cached options，4-tuple in-memory filter）；主查詢端點新增六個 additive 可選 body 欄位（`pj_packages[]`、`pj_bops[]`、`pj_functions[]`、`mfg_orders[]`、`lot_ids[]`、`wafer_lots[]`）；萬用字元語法與安全性規則見 business-rules.md PHF-01..PHF-06；全部 backward-compatible。
- **2026-05-13（resource-history-perf）：** `resource_history_routes.py` 新增 `GET /api/resource/history/query/progress` 端點；progress state 以 Redis side-channel 儲存；auth required；400/404 error contract；additive，不影響既有端點及 Type A re-query 流程。
- **2026-05-18（equipment-rejects-by-lots）：** `query_tool_routes.py` `POST /api/query-tool/equipment-period` (`query_type='rejects'`) and `POST /api/query-tool/export-csv` (`export_type='equipment_rejects'`) response shape changed to per-reject-event detail rows (see api-contract.md §10). Breaking cutover — both consumer views shipped atomically.
- **2026-05-13（wip-hold-drilldown-filters）：** `wip_routes.py` 四個端點新增三個可選過濾參數（`workflow`、`bop`、`pj_function`）；`/detail/<workcenter>` lot 列新增 `pjType`；`/meta/filter-options` response 新增 `workflows`、`bops`、`pjFunctions`；全部 backward-compatible。
- **2026-04-15：** 所有 `standard-json` 端點注入 `meta.app_version`（additive，backward-compatible）。
- **2026-03-11：** `/health` / `/health/deep` 加入 `system_memory` + `async_workers`（backward-compatible）。

---

## Contract Change Checklist

- [ ] 端點新增/刪除/重新命名/搬移已反映在正確分類區段。
- [ ] 新或改動的 standard-json 端點確認使用 `success_response()` / `error_response()`。
- [ ] 例外端點更新包含原因、影響範圍與對應驗證說明。
- [ ] 相關 API tests/contract checks 已在同一變更更新。

## Synchronization Rule

任何新增/刪除/重新命名/搬移 API 端點或改變分類，必須在同一變更同步更新此盤點清單。

## Categories

- standard-json
- health-exception
- stream-download-exception
- internal-only
- legacy-transition
