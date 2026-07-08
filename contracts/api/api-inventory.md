---
contract: api-inventory
summary: Endpoint inventory categories and ownership map for non-standard API surfaces.
owner: application-team
surface: api
schema-version: 1.5.0
last-changed: 2026-07-04
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
| `hold_overview_routes.py` | All JSON API endpoints — `/summary`, `/matrix`, `/treemap`, `/lots` 接受 `POST` JSON body；`reason` 可為 CSV string (GET) 或 JSON array (POST)；`/lots` 新增可選 `export` boolean 參數（GET: `?export=true`, POST body: `"export": true`），export 模式下略過 per_page 上限，回傳全量匹配列（上限 `HOLD_OVERVIEW_EXPORT_MAX_ROWS`）；不含 `export` 時行為完全不變（hold-overview-export-csv，additive）。 |
| `hold_history_routes.py` | All JSON API endpoints — **Type A** (sync re-query on 410); **Also Type B** for `POST /api/hold-history/query` when date range ≥ `HOLD_ASYNC_DAY_THRESHOLD` AND `HOLD_ASYNC_ENABLED=true` → HTTP 202 `{async:true, job_id, status_url=/api/job/<id>?prefix=hold-history}`; short-range or flag-off → HTTP 200 sync unchanged (hold-history-rq-async)；`duration` payload: `{ items: [{range, count, qty, pct}], avgReleasedHours, avgOnHoldHours, maxReleasedHours, maxOnHoldHours }`；trend day 含 `repeatQualityHoldQty`；**`POST /api/hold-history/today-snapshot`**: inputs `{ hold_type, record_type, reason, duration_range, page, per_page }`，response `{ query_id, summary: { onHoldLots, onHoldQty, todayNewQty, todayReleaseQty, todayFutureHoldQty, repeatQualityHoldQty, onHoldAvgHours, onHoldMaxHours }, reason_pareto, duration, list }`；cache `hold_today:*` TTL 60s；DB 不可用 → 503 `service_unavailable`；detail list 每筆明細列新增 `package: string \| null`（add-package-detail-tables，additive） |
| `reject_history_routes.py` | All JSON API endpoints — **Type B** (async 202 polling on 410)；含 `GET /api/reject-history/job/<job_id>`；`/batch-pareto` / `/view` 接受 `POST` JSON body；`POST /api/reject-history/query` 新增四個可選 body 欄位（`pj_types[]`、`packages[]`、`pj_functions[]`、`reasons[]`，全部為 string 陣列，additive；缺省或空陣列時行為與舊版完全一致）；過濾條件注入 `{{ BASE_WHERE }}` 層（Oracle CTE 內，`reject_raw` GROUP BY 之前）；`reasons[]` 對應 `NVL(TRIM(r.LOSSREASONNAME), '(未填寫)') IN (...)` 語意（sentinel `(未填寫)` 有別於 container-level `(NA)`）；`workcenter_groups[]` 參數已移除；supplementary `{{ WHERE_CLAUSE }}` 過濾層（workcenter_groups、packages、reasons、types）整體移除（rh-primary-prefilter + rh-remove-supplementary-filter）|
| `resource_routes.py` | All JSON API endpoints — `/status`、`/status/summary`、`/status/matrix` 新增可選查詢參數 `package_groups`（逗號分隔字串，resource-status-package-group）；`/status/options` response 新增 `package_groups: string[]`；`/status` response record 新增 `PACKAGEGROUPNAME: string \| null`（PACKAGEGROUPID NULL 時為 null）。 |
| `resource_history_routes.py` | All JSON API endpoints — **Type A** (sync re-query on 410); **Also Type B** for `POST /api/resource/history/query` when date range ≥ `RESOURCE_ASYNC_DAY_THRESHOLD` AND `RESOURCE_ASYNC_ENABLED=true` → HTTP 202 `{async:true, job_id, status_url=/api/job/<id>?prefix=resource-history}`; short-range or flag-off → HTTP 200 sync unchanged (resource-history-rq-async)；`POST /api/resource/history/query` 先查 canonical base spool（DuckDB filter）；response: `{query_id, summary, detail}`；**新增** `GET /api/resource/history/query/progress?query_id=<uuid>` — batch 查詢進度 side-channel；progress state 存於 Redis key `resource:history:progress:<query_id>`；400 on missing param，404 on unknown query_id；auth required（與其他端點相同 `login_required` guard）（resource-history-perf）。 |
| `yield_alert_routes.py` | All JSON API endpoints — **Type B** (async 202 polling) for initial query; **Type A** (spool-only, 410 on miss) for all view endpoints after query. `POST /api/yield-alert/query` accepts optional `process_type` (enum: `"GA%"` default / `"GC%"`); omitting defaults to `"GA%"`. `GET /api/yield-alert/alerts` rows gain `source_code: string \| null` (LOT ID; null = workorder-level; NOT NULL ⇒ TX=0). All four views (trend, summary, heatmap, alerts) now served from `yield_alert_dataset` DuckDB spool only — live Oracle trend/summary query paths retired. Spool gains `process_type`, `SOURCE_CODE`, `REJECT_LINKED` columns; `_SCHEMA_VERSION` bump + `rm -f tmp/query_spool/yield_alert_dataset/*.parquet` required on deploy/rollback. `GET /api/yield-alert/cross-filter-options?query_id=...&lines[]=...&packages[]=...`, 410 on spool expired. (yield-alert-spool-refactor) |
| `production_history_routes.py` | All JSON API endpoints — `POST /api/production-history/query` 驗證 `pj_types`, `start_date`, `end_date`；缺少/無效 → 400 `VALIDATION_ERROR`；date range > 730d → 400；spool hit → 200，miss+RQ → 202；含 `POST /page`（DuckDB paged）、`/matrix`、`/options`；gated by `PROD_HISTORY_ENABLED`。**新增** `GET /api/production-history/filter-options?selected=<json>` — cross-filter cached options（4-tuple in-memory filter over `container_filter_cache`），auth required，400 on malformed `selected` JSON，404 on cache cold start failure，500 on Oracle build error；payload schema `{data: {pj_types, packages, bops, pj_functions}, meta: {updated_at, schema_version: 2}}`（prod-history-first-tier-cache-filters）。主查詢端點 `POST /api/production-history/query` 新增可選欄位 `pj_packages[]`、`pj_bops[]`、`pj_functions[]`（cached MultiSelect，plain `IN`）、`mfg_orders[]`、`lot_ids[]`、`wafer_lots[]`（多行 + `*` 萬用字元，依 PHF-02 規則 `LIKE ESCAPE '\'` bind）；全部 additive、缺省時保持 Type-only 行為。`start_date` / `end_date` 自 prod-history-query-mode-tabs 起為**條件必填**：classification mode（無 identifier token）仍必填；identifier mode（含 `mfg_orders` / `lot_ids` / `wafer_lots` token）可省略，省略時走 wide / all-time 查詢。 |
| `admin_routes.py` | `GET /admin/api/pages` (slimmed; returns `{pages:[{route,status}]}`; admin required)、`PUT /admin/api/pages/<route>` (status-only; accepts only `{status}`; admin required)、`GET /admin/api/user-usage-kpi`（params: `start_date`, `end_date`, `department`）、`POST /admin/api/analytics/recalculate`（admin required）. **REMOVED (nav-config-to-code):** `GET /admin/api/drawers`, `POST /admin/api/drawers`, `PUT /admin/api/drawers/{drawer_id}`, `DELETE /admin/api/drawers/{drawer_id}` → all 404. |
| `job_query_routes.py` | All JSON API endpoints |
| `qc_gate_routes.py` | All JSON API endpoints |
| `trace_routes.py` | All JSON API endpoints — `GET /api/trace/lineage/job/<job_id>` / `/result`；`POST /api/trace/lineage` 非同步 capable → 202；MSD events → `{spool_hit, trace_query_id, aggregation}`；`trace_query_id` 為 stable hash-based canonical query id |
| `mid_section_defect_routes.py` | All JSON API endpoints — **compatibility adapter**：`GET /api/mid-section-defect/analysis` accepts optional `pj_types[]` and `packages[]` multi-value params (post-query filter on detection_df; AND-semantics; absent/empty = no restriction); `/analysis/detail` / `/export` accept optional `trace_query_id`. **New**: `GET /api/mid-section-defect/container-filter-options?selected=<json>` — cross-filter cached options; 400 on malformed `selected` JSON; 500 on Oracle build error (msd-type-package-filter). **Forward fields (msd-forward-cause-effect)**: `direction=forward` adds `by_detection_loss_reason[]`, `loss_reason_workcenter_crosstab`, `downstream_trend[]`, `amplification` to `/analysis` response; `/analysis/detail` rows gain `DETECTION_LOSS_REASON`. |
| `query_tool_routes.py` | All JSON API endpoints；`GET /api/query-tool/lot-history` 和 `POST /api/query-tool/equipment-period`（`query_type=lots`）每筆 row 新增 `PRODUCTLINENAME: string \| null`（add-package-detail-tables，additive）；`POST /api/query-tool/equipment-period`（`query_type=rejects`）`PRODUCTLINENAME` 已存在（equipment_lot_rejects.sql line 52） |
| `material_trace_routes.py` | JSON endpoints（CSV export 除外）— `POST /api/material-trace/query` spool 優先；miss → 202；RQ 不可用 → 503+Retry-After；`GET /api/material-trace/job/<job_id>`；`POST /api/material-trace/export` 需 `query_hash`，409 `QUERY_NOT_READY` if not ready |
| `db_scheduling_routes.py` | `GET /api/db-scheduling/queue` — read-only recommendation endpoint; queries `DWH.DW_MES_LOT_V` (5-min WIP cache); sync only (~689 lots); returns recommended DB equipment per D/B-START lot; WORKFLOWNAME-match primary path + BOP-fallback (DB-01..DB-05); matchSource enum: workflow/bop-fallback/none. Auth required. `GET /api/db-scheduling/equipment-detail?equipment=<id>` — on-demand machine status + running-lot detail from realtime-equipment-cache + WIP cache; 400 if equipment param missing. Auth required. |
| `production_achievement_routes.py` | All JSON API endpoints — **Type B** (async 202 polling, `always_async=True`, no sync fallback — clean pre-launch replacement, mirrors `resource_history_routes.py`) for `GET /report`: canonical spool key is `(start_date, end_date, _PA_SPOOL_SCHEMA_VERSION)` (date-range only; `shift_code`/`workcenter_group` no longer filter the server response — PA-06/PA-07 rollup+target-join+achievement_rate now computed client-side in DuckDB-WASM from the SPECNAME-grain spool, data-shape-contract.md §3.28); spool-hit → HTTP 200 `{query_id, spool_download_url, spec_workcenter_map, targets_map}`; spool-miss + worker available → HTTP 202 `{async:true, job_id, status_url=/api/job/<id>?prefix=production-achievement}` (reuses the generic job-status endpoint, no domain-specific `/job/<job_id>` route); spool-miss + worker unavailable → HTTP 503. PA-05 predicate applied at Oracle query time against `DW_MES_LOTWIPHISTORY` inside the new `ProductionAchievementJob` (`BaseChunkedDuckDBJob`, `chunk_strategy=TIME`, re-aggregating `post_aggregate` — ADR-0016). Gated by `PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB` (env-contract.md, default `on`); `off` = kill switch → spool-miss returns 503 (no legacy path). `GET /filter-options`; `GET /targets` (view-only, no permission gate); `PUT /targets` (permission-gated by new `can_edit_targets` check, independent of `admin_required`; writes new MySQL table `production_achievement_targets` directly via `core/mysql_client.py`, bypassing `core/sync_worker.py`; requires `MYSQL_OPS_ENABLED=true`) — unchanged by `production-achievement-async-spool`. Admin whitelist endpoints (`GET`/`PUT /admin/api/production-achievement/permissions*`) live in the same module, unchanged. Auth required. (production-achievement-async-spool) |
| `eap_alarm_routes.py` | All JSON API endpoints — **Type B** (async 202 for `POST /api/eap-alarm/spool`; client polls `GET /api/job/<id>?prefix=eap-alarm`); fine-filter views (`GET /summary`, `/pareto`, `/trend`, `/detail`, `/filter-options`) served from `eap_alarm` DuckDB spool only (no Oracle re-query post-spool; 410 `CACHE_EXPIRED` on spool miss). Spool key: `eap_alarm:{date_from}:{date_to}:{sorted_eqp_types_hash}`. AlarmCategory decoded per EA-05 fixed table; unknown code → `"未知"` fallback. LAST_UPDATE_TIME mandatory index filter applied at Oracle query time (business-rules.md EA-03). `_ALLOWED_NAMESPACES` must include `"eap_alarm"`. |
| `material_consumption_routes.py` | All JSON API endpoints — **Type B** (async 202 for detail; summary always sync)；`GET /api/material-consumption/filter-options` → `{workcenter_groups, primary_categories, pj_types}`；`POST /api/material-consumption/query` → summary spool sync → `{query_id, kpi, trend[], type_breakdown[]}`；`GET /api/material-consumption/view?query_id=&granularity=` → DuckDB regroup of summary spool（no Oracle；410 on spool miss）；`POST /api/material-consumption/detail` → sync 200 when rows ≤ SYNC_ROW_LIMIT，else 202 async；`GET /api/material-consumption/detail/page?query_id=&page=` 每筆 row 新增 `PRODUCTLINENAME: string \| null`（add-package-detail-tables，additive；detail spool parquet schema updated — `rm -f tmp/query_spool/material_consumption/detail-*.parquet` required on deploy/rollback）；`GET /api/material-consumption/detail/job/<job_id>` → `{status: pending\|running\|done\|failed, query_id?}`；`material_parts` cap 20，`*` wildcard allowed（MC-01 / MC-02）。 |
| `downtime_analysis_routes.py` | All JSON API endpoints — **Type A raw-spool** (flag ON) / **Type A enriched-spool** (flag OFF); `GET /api/downtime-analysis/options` → `{workcenter_groups[], families[], resources[], package_groups[], big_categories[], reasons[]}`; `POST /api/downtime-analysis/query` → Oracle or DuckDB prewarm → (flag ON) `{base_spool_url, jobs_spool_url, query_id, taxonomy}` (browser-DuckDB path; spool namespaces `downtime_analysis_base_events`, `downtime_analysis_job_bridge`; `SCHEMA_VERSION` in cache key) / (flag OFF) `{query_id, summary: DowntimeKpiShape, daily_trend[], big_category[], top_reasons[]}` (legacy enriched-spool path; spool namespace `downtime_analysis_events`; cache key includes `DOWNTIME_BRIDGE_VERSION`); `GET /api/downtime-analysis/view` → **[DEPRECATED: removal target api 1.17.0]** DuckDB regroup (no Oracle; 410 on spool miss); `GET /api/downtime-analysis/equipment-detail` → **[DEPRECATED: removal target api 1.17.0]** `{equipment_detail: EquipmentDetailRow[]}`; `GET /api/downtime-analysis/event-detail` → **[DEPRECATED: removal target api 1.17.0]** `{events: paginated EventDetailRow[]}`. DA-01..DA-08 apply. Feature flag: `DOWNTIME_BROWSER_DUCKDB` (default false). |
| `analytics_routes.py` | `GET /api/analytics/yield-anomalies`, `/reject-spikes`, `/hold-outliers`, `/equipment-deviation`, `/anomaly-summary` 及各 `/drilldown`；gated by `ANALYTICS_ANOMALY_DETECTION_ENABLED`；`anomaly-summary` 注入 `meta.cache_state` |
| `user_auth_routes.py` | `POST /api/auth/login` (public, rate-limited 5/5min, JSON `{username, password}`)、`POST /api/auth/logout`、`GET /api/auth/me`（null if not logged in）、`PATCH /api/auth/heartbeat` (login_required) |
| `ai_routes.py` | `POST /api/ai/query` — NL query；`AI_MODE` 決定 pipeline；function mode 使用 combined call（select+fill 合一），text2sql mode 注入 chat_history 至 Stage 1；leader mode（leader/subagent 分層）response 額外含 additive `subtasks: [{goal, answer, success}]`；response: `{answer, chart_data, query_used, params_used, suggestions, sql_used, tool_trace, needs_clarification}`；新增三個 AI 函式（production_history_query、resource_history_summary、qc_gate_status）；route surface 不變；gated by `AI_QUERY_ENABLED` |
| `job_routes.py` | `GET /api/job/<job_id>?prefix=<p>` — async 狀態；`POST /api/job/<job_id>/abandon` — idempotent，rate-limited 30/60s |

## Admin Page Routes（非 API）

| File | Routes | Notes |
|---|---|---|
| `admin_routes.py` | `/admin/performance`, `/admin/user-usage-kpi`, `/admin/dashboard` | `/admin/performance` and `/admin/user-usage-kpi` are redirect-only stubs (HTTP 302 → `/admin/dashboard`), not SPA HTML routes. `/admin/dashboard` is the live Admin-auth SPA HTML entry; CSRF token injected into HTML. |

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
| `eap_alarm_routes.py` | All JSON API endpoints — **Type B** (async 202 for `POST /api/eap-alarm/spool`; client polls `GET /api/job/<id>?prefix=eap-alarm`); fine-filter views (`GET /summary`, `/pareto`, `/trend`, `/detail`, `/filter-options`) served from `eap_alarm` DuckDB spool only (no Oracle re-query post-spool; 410 `CACHE_EXPIRED` on spool miss). Spool key: `eap_alarm:{date_from}:{date_to}:{sorted_eqp_types_hash}`. AlarmCategory decoded per EA-05 fixed table; unknown code → `"未知"` fallback. LAST_UPDATE_TIME mandatory index filter applied at Oracle query time (business-rules.md EA-03). `_ALLOWED_NAMESPACES` must include `"eap_alarm"`. |
| `material_consumption_routes.py` | `POST /api/material-consumption/export` — chunked CSV stream of detail spool via DuckDB；no full-memory load |
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
| `app.py` | `/api/portal/navigation` | Status feed; returns `{statuses, is_admin, admin_user, admin_links, features, diagnostics}`; drawers dropped (nav-config-to-code) |

## Excluded

| File | Reason |
|---|---|
| `auth_routes.py` | Admin login/logout pages (`/admin/*`)，非 `/api/*` scope |

---

## Compatibility Notes

- **2026-07-02 (production-achievement-kanban):** `production_achievement_routes.py` — new module; 4 additive endpoints under `/api/production-achievement/*` plus 2 admin whitelist endpoints. Reads `DW_MES_LOTWIPHISTORY` via Oracle; writes/reads two new independent MySQL tables directly via `core/mysql_client.py` (target values, edit-permission whitelist) — explicitly NOT via `core/sync_worker.py` SQLite dual-layer sync (that path is one-way/eventually-consistent, max 10-min lag, unsuitable for immediate-consistency permission/target reads). No existing routes changed.

- **2026-06-24 (nav-config-to-code):** `admin_routes.py` — 4 drawer endpoints removed (GET/POST/PUT/DELETE `/admin/api/drawers*`); `GET /admin/api/pages` slimmed to `{pages:[{route,status}]}`; `PUT /admin/api/pages/<route>` body narrowed to `{status}` only. `app.py` — `/api/portal/navigation` inverted from drawer-tree to status feed `{statuses, is_admin, admin_user, admin_links, features, diagnostics}`; drawers dropped. Breaking; monorepo atomic cutover.

- **2026-06-18 (eap-alarm-analysis):** `eap_alarm_routes.py` — new module; 7 additive endpoints. `POST /api/eap-alarm/spool` always dispatches via RQ Type B (no date-range threshold; always async when worker available). Fine-filter options derived from DuckDB spool. Spool namespace `eap_alarm`. No existing routes changed.

- **2026-06-15 (resource-history-rq-async):** `resource_history_routes.py` — `POST /api/resource/history/query` gains optional async 202 path (env-gated; additive). Date range ≥ `RESOURCE_ASYNC_DAY_THRESHOLD` (default 90) + `RESOURCE_ASYNC_ENABLED=true` + worker available → 202 `{async, job_id, status_url=/api/job/<id>?prefix=resource-history}`; otherwise HTTP 200 sync (unchanged). No endpoint added or removed. New RQ queue `resource-history-query`. Flag-off restores sync with no redeploy.
- **2026-06-13 (hold-history-rq-async):** `hold_history_routes.py` — `POST /api/hold-history/query` gains optional async 202 path (env-gated; additive). Date range ≥ `HOLD_ASYNC_DAY_THRESHOLD` (default 90) + `HOLD_ASYNC_ENABLED=true` + worker available → 202 `{async, job_id, status_url}`; otherwise HTTP 200 sync (unchanged). No endpoint added or removed. New RQ queue `hold-history-query`. Flag-off restores sync with no redeploy.
- **2026-06-12 (downtime-browser-duckdb):** `downtime_analysis_routes.py` — `POST /api/downtime-analysis/query` response shape changed when `DOWNTIME_BROWSER_DUCKDB=true` (default false at initial ship): returns `{base_spool_url, jobs_spool_url, query_id, taxonomy}` instead of `{query_id, summary, daily_trend, big_category, top_reasons}`. Three endpoints deprecated in-place (removal target api 1.17.0): `GET /api/downtime-analysis/view`, `GET /api/downtime-analysis/equipment-detail`, `GET /api/downtime-detail/event-detail`. 90-day Oracle-path guard (`_MAX_ORACLE_DAYS`) removed; 730-day SYS-04 cap retained. Flag-off restores prior shape with no redeploy. Raw spool namespaces: `downtime_analysis_base_events`, `downtime_analysis_job_bridge`; `SCHEMA_VERSION` in cache key.
- **2026-06-03 (downtime-analysis-page-redesign):** `downtime_analysis_routes.py` — additive optional params on two existing endpoints: `GET /api/downtime-analysis/equipment-detail` gains `big_category` and `status_types` (CSV, opt); `GET /api/downtime-analysis/event-detail` gains `big_category`, `status_types`, and `resource_id` (all opt). Filtering in in-memory parquet spool; no Oracle re-query. Response wrapper keys (`equipment_detail`, `events`) and per-row schemas unchanged. Backward-compatible.
- **2026-05-29 (downtime-analysis-page):** `downtime_analysis_routes.py` new (new page); 5 endpoints all additive; spool namespace `downtime_analysis_*` independent of `resource_dataset_*`; cache key versioned with `DOWNTIME_BRIDGE_VERSION`. No existing endpoint changed.
- **2026-05-22（add-package-detail-tables）：** `hold_history_routes.py` hold-detail list rows 新增 `package: string | null`；`query_tool_routes.py` lot-history 和 equipment-lots rows 新增 `PRODUCTLINENAME: string | null`；equipment-rejects `PRODUCTLINENAME` 已存在，前端補顯示；`material_consumption_routes.py` detail/page rows 新增 `PRODUCTLINENAME: string | null`（detail spool schema change — parquet cleanup required on deploy/rollback）；全部 additive，backward-compatible。
- **2026-05-20（material-part-consumption）：** `material_consumption_routes.py` 新增（新頁面）；7 個端點全部 additive；`POST /query` / `GET /view` / `GET /detail/page` / `GET /detail/job` 為 standard-json；`POST /export` 為 stream-download-exception；無既有端點變更；summary 查詢 always sync；detail 查詢 sync ≤ SYNC_ROW_LIMIT，else async Type B（RQ queue `material-consumption`）。
- **2026-05-19（fix-admin-dashboard）：** `admin_routes.py` `/admin/api/performance-detail` `data.redis` 新增 `evicted_keys`、`expired_keys`、`mem_fragmentation_ratio`、`slowlog` 四 key；新增 `data.duckdb` 子物件（`temp_dir_bytes`、`memory_limit_state`）；`/admin/api/logs` 查詢範圍擴大至含已同步記錄，pagination 修正；全部 backward-compatible，無端點新增/移除。
- **2026-05-14（prod-history-query-mode-tabs）：** `production_history_routes.py` 主查詢端點 `POST /api/production-history/query` 的 `start_date` / `end_date` 由無條件必填放寬為條件必填（classification mode 必填、identifier mode 可選）；無端點新增/刪除/重新命名；backward-compatible。Per-mode 驗證規則見 business-rules.md PHF-07 / PHF-08。
- **2026-05-14（prod-history-first-tier-cache-filters）：** `production_history_routes.py` 新增 `GET /api/production-history/filter-options` 端點（cross-filter cached options，4-tuple in-memory filter）；主查詢端點新增六個 additive 可選 body 欄位（`pj_packages[]`、`pj_bops[]`、`pj_functions[]`、`mfg_orders[]`、`lot_ids[]`、`wafer_lots[]`）；萬用字元語法與安全性規則見 business-rules.md PHF-01..PHF-06；全部 backward-compatible。
- **2026-05-13（resource-history-perf）：** `resource_history_routes.py` 新增 `GET /api/resource/history/query/progress` 端點；progress state 以 Redis side-channel 儲存；auth required；400/404 error contract；additive，不影響既有端點及 Type A re-query 流程。
- **2026-05-18（equipment-rejects-by-lots）：** `query_tool_routes.py` `POST /api/query-tool/equipment-period` (`query_type='rejects'`) and `POST /api/query-tool/export-csv` (`export_type='equipment_rejects'`) response shape changed to per-reject-event detail rows (see api-contract.md §10). Breaking cutover — both consumer views shipped atomically.
- **2026-05-13（wip-hold-drilldown-filters）：** `wip_routes.py` 四個端點新增三個可選過濾參數（`workflow`、`bop`、`pj_function`）；`/detail/<workcenter>` lot 列新增 `pjType`；`/meta/filter-options` response 新增 `workflows`、`bops`、`pjFunctions`；全部 backward-compatible。
- **2026-04-15：** 所有 `standard-json` 端點注入 `meta.app_version`（additive，backward-compatible）。
- **2026-06-25 (rh-primary-prefilter):** `reject_history_routes.py` — `POST /api/reject-history/query` body gains three additive optional fields: `pj_types[]`, `packages[]`, `pj_functions[]`. Injected into `{{ BASE_WHERE }}` of `reject_raw` CTE (Oracle layer, before GROUP BY). Backward-compatible; absent/empty = no restriction. Sole consumer: `frontend/src/reject-history/`.
- **2026-06-25 (rh-remove-supplementary-filter):** `reject_history_routes.py` — `POST /api/reject-history/query` gains `reasons[]` (string array; `NVL(TRIM(r.LOSSREASONNAME), '(未填寫)') IN (...)`; injected into `{{ BASE_WHERE }}`; sentinel `(未填寫)` distinct from container-level `(NA)`). `workcenter_groups[]` removed. Supplementary `{{ WHERE_CLAUSE }}` filter layer fully removed. Sole consumer `frontend/src/reject-history/`; monorepo atomic cutover.
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
