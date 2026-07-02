---
contract: business
summary: Business decision tables, rule inventory, and change policy for behavior updates.
owner: application-team
surface: domain-behavior
schema-version: 1.42.0
last-changed: 2026-07-02
breaking-change-policy: deprecate-2-minors
---

# Business Rules — MES Dashboard

> 來源：整合自 `PRD.md`、`contract/api_inventory.md` 及已知 hold-history 行為（2026-05-05）

## System-level Rules

| rule id | name | current behavior | tests |
|---|---|---|---|
| SYS-01 | Concurrent user capacity | 支援 50 人使用 / 10-12 人同時在線；超載時非同步 job 排隊，不阻塞介面 | stress gate |
| SYS-02 | Cache hit performance target | 快取命中回應 ≤ 2s；重查詢走非同步不卡介面 | soak gate |
| SYS-03 | Feature flag gating | AI query（`AI_QUERY_ENABLED`）、anomaly detection（`ANALYTICS_ANOMALY_DETECTION_ENABLED`）、production history（`PROD_HISTORY_ENABLED`）均以 env 控制；disabled 時端點直接 404 或不掛載 | unit tests |
| SYS-04 | Max date range | 日期區間查詢上限 730 天（production-history 驗證；其他模組參考此上限） | route tests |
| SYS-05 | Read-only | MES Dashboard 僅查詢 MES 資料庫，不修改任何生產數據 | — |

## Auth Rules

| rule id | name | current behavior | tests |
|---|---|---|---|
| AUTH-01 | Login rate limit | `POST /api/auth/login` rate-limited 5 req / 5 min（per IP） | route tests |
| AUTH-02 | Session lifetime | 預設 28800s（8h）；`PERMANENT_SESSION_LIFETIME` 控制 | — |
| AUTH-03 | Admin check | `is_admin` flag 從 LDAP `ADMIN_EMAILS` 名單判斷；admin 端點多一層 decorator | unit tests |
| AUTH-04 | Local auth | `LOCAL_AUTH_ENABLED=true` 時允許本地帳號登入（僅開發用；production 禁用） | — |

## Async Job Rules

| rule id | name | current behavior | tests |
|---|---|---|---|
| ASYNC-01 | Type A — sync re-query on cache miss | view miss → 410 `CACHE_EXPIRED` → client 同步重觸發 query；適用：hold-history、resource-history | resilience tests |
| ASYNC-02 | Type B — 202 polling on cache miss | query miss + RQ available → 202 `{async, job_id, status_url}`；client polling；RQ unavailable → fallback sync 200；適用：reject-history、yield-alert、production-history、trace、material-trace | resilience tests |
| ASYNC-03 | Job abandon | `POST /api/job/<job_id>/abandon` idempotent；已 terminal 的 job 回傳 409；已放棄的 job 回傳 200 | route tests |
| ASYNC-04 | Job ownership | 若 job metadata 含 `owner`，caller 必須提供匹配的 `owner` 值；否則 403 `FORBIDDEN` | route tests |
| ASYNC-05 | Progress milestone semantics | Services that call `update_job_progress(pct, stage)` MUST follow the canonical milestone map: `pct=0` (job start), `pct=30` (Oracle query issued, `stage="querying"`), `pct=100` (data written to spool, `stage="complete"`). Intermediate milestones are additive; omitting them for a service is permitted. Services that do not call `update_job_progress` omit `pct`/`stage` entirely from the job status payload. Consumer (`AsyncQueryProgress.vue`) MUST treat absent `pct` as indeterminate (show spinner, not 0%). | unit tests (backend pct-milestone, frontend composable) |
| ASYNC-06 | Always-async 503 on forced sync | When `JobTypeConfig.always_async=True` AND `sync_fallback_allowed=False` AND async queue unavailable: the request MUST receive HTTP 503 `SERVICE_UNAVAILABLE` with a `Retry-After` header. It MUST NOT be silently downgraded to synchronous execution. Rationale: always-async domains (e.g. eap_alarm) have query durations that exceed safe synchronous timeout bounds; a partial synchronous result would be incorrect and misleading. Cross-reference: error-format.md §503 Async Unavailable. | `tests/test_async_query_job_service.py` (AC-4) |
| ASYNC-07 | Unified-job dispatch (production_history + reject) | When `PRODUCTION_HISTORY_USE_UNIFIED_JOB=on` OR `REJECT_HISTORY_USE_UNIFIED_JOB=on`, the respective route MUST enqueue via `enqueue_query_job("<domain>_unified", ..., sync_fallback_allowed=True)` with `JobTypeConfig.always_async=False`. Queue unavailable: the route MAY fall back to legacy path or return 503 (sync_fallback_allowed=True means no forced 503). Queue available → HTTP 202. Flag `off` (default): the legacy enqueue path runs verbatim (AC-8 zero-regression). Both domain flags are independent per-domain rollback handles. Added by change `production-reject-history-migration`. | `tests/test_async_query_job_service.py::TestProductionHistoryUnifiedJobRegistry`, `tests/test_async_query_job_service.py::TestRejectHistoryUnifiedJobRegistry` |
| ASYNC-08 | OOM guard shift (reject domain) | The unified job worker path (`reject_history_worker.py`) writes raw rows to the canonical spool via DuckDB COPY: no pandas heap allocation occurs, so no post-hoc memory check can trigger. Pre-emptive OOM protection: DuckDB on-disk spill (`DUCKDB_JOB_DIR`) handles memory pressure at the storage layer before any Python heap pressure. The legacy flag=off path retains its existing memory-pressure checks (`_enforce_interactive_memory_guard`, RSS-pressure guard) unchanged — no regression. The `TestOomGuardAbsence` test verifies that the new worker modules and the legacy source files contain no `if len(df)…: raise` or `memory_usage`-as-IF-condition raise patterns; the legacy path uses RSS-pressure and helper delegation (not these patterns), so the test confirms both paths are free of that specific guard class. Added by change `production-reject-history-migration`. | `tests/test_reject_history_unified_job.py::TestOomGuardAbsence` |
| ASYNC-09 | Dual-job unified execution (resource-history domain) | When `RESOURCE_HISTORY_USE_UNIFIED_JOB=on`, the export route MUST enqueue TWO separate RQ jobs: (1) `ResourceHistoryBaseJob` (`resource-history-base`, `requires_cross_chunk_reduction=False`) writing to `resource_dataset` spool, and (2) `ResourceHistoryOeeJob` (`resource-history-oee`, `requires_cross_chunk_reduction=True`) writing to `resource_oee` spool. Both jobs use `always_async=True` and `sync_fallback_allowed=False`. When the async queue is unavailable the route returns HTTP 503 with Retry-After (no silent sync downgrade). The OEE job computes ratio-of-SUMs (`yield = ΣTRACKOUT/(ΣTRACKOUT+ΣNG)`) across all chunks via job-temp DuckDB `post_aggregate`; per-chunk pre-aggregation is not used (ADR-0003 cross-chunk reduction). Each OEE chunk's `:reject_start`/`:reject_end` binds are widened ±30 days around the chunk's production dates to prevent boundary-NG loss. Flag `off` (default): the legacy `export_csv` Oracle read + pandas iterrows path is used unchanged (AC-1 zero-regression). Spool parquet schemas for `resource_dataset` and `resource_oee` are identical to the legacy path (§3.19 data-shape-UNCHANGED). Added by change `resource-history-migration`. | `tests/test_resource_history_unified_job.py`, `tests/test_resource_history_job_service.py` |
| ASYNC-10 | Unified-job dispatch (material-trace domain) | When `MATERIAL_TRACE_USE_UNIFIED_JOB=on`, the `api_material_trace_query` route MUST dispatch via `enqueue_query_job("material-trace-unified", ..., sync_fallback_allowed=False)` with `JobTypeConfig.always_async=True`. If the async queue is unavailable, the route MUST return HTTP 503 SERVICE_UNAVAILABLE with Retry-After — no silent sync fallback (D4 decision: the in-request legacy pandas path is the OOM risk the flag exists to eliminate). Queue available → HTTP 202 with `{async, job_id, status_url, query_hash}`. The `MaterialTraceJob` (BaseChunkedDuckDBJob, `chunk_strategy=ID_LIST`, `requires_cross_chunk_reduction=False`) uses ID-list batching (1000/batch, `_IN_BATCH_SIZE=1000`), Arrow-to-DuckDB streaming, and `post_aggregate` DISTINCT on `[CONTAINERID, MATERIALLOTNAME, WORKCENTERNAME, TXNDATE]` (exact 4-column dedup key from legacy L238). WORKCENTER_GROUP enrichment is applied inside `post_aggregate` before COPY TO spool. Spool namespace `material_trace` and parquet schema are unchanged — frontend `/view` and CSV export need no change. Flag `off` (default): the legacy `_execute_batched_query_to_parquet` streaming path is used verbatim (AC-1 zero-regression). Added by change `material-trace-streaming-migration`. | `tests/test_material_trace_unified_job.py` |
| ASYNC-11 | Heavy-query semaphore role re-statement (D3) | `global_concurrency.acquire_heavy_query_slot` (Lua CAS over a Redis sorted set, `HEAVY_QUERY_MAX_CONCURRENT` default 3, fail-open) has no code change in this migration. Its semantic role shifts from "throttle synchronous slow queries blocking gunicorn workers" to "cap concurrent RQ heavy jobs hitting Oracle simultaneously". Per-job chunk fan-out is bounded separately by `BaseChunkedDuckDBJob.max_parallel` (default 3). No new env var, no CAS logic change. This rule documents the semantic shift only; no implementation change is required. Added by change `material-trace-streaming-migration`. | — (semantics-only, no test) |
| ASYNC-12 | Query-tool RQ async dispatch (AC-1, D1) | When `QUERY_TOOL_USE_RQ=on`, `classify_query_cost(domain="query_tool", ...)` returns ASYNC, and `is_async_available()=True`, the `POST /api/query-tool/equipment-period` route MUST enqueue via `enqueue_query_job("query-tool", ..., sync_fallback_allowed=True)` and return HTTP 202 `{async: true, job_id, status_url}`. When flag=off (default), date span < threshold, or queue unavailable, the route falls through to the existing inline sync path (200). Fail-open: enqueue failure → sync fallback (no 503). The `query-tool` job type uses `always_async=False` so sync fallback is always permitted. Added by change `query-path-c-elimination-cleanup`. | `tests/integration/test_query_tool_rq_async.py` |
| ASYNC-13 | WIP detail rowcount pre-check (AC-3, D2) | `GET /api/wip/detail/<workcenter>` route performs a lightweight `SELECT COUNT(*)` via `count_wip_rows(...)` with the same filtered predicate as the detail query BEFORE calling `get_wip_detail`. When count >= L3 (200,000 rows) and async is available, the route attempts RQ dispatch. COUNT failure returns 0 (fail-open → SYNC). WIP has no date range so L2 never fires — only L3 matters. Added by change `query-path-c-elimination-cleanup`. | `tests/integration/test_wip_rowcount_rq_routing.py` |
| ASYNC-14 | merge_chunks deprecation — no new callers (AC-4, D5) | `batch_query_engine.merge_chunks` is deprecated as of `query-path-c-elimination-cleanup` (P5). It emits `DeprecationWarning` on every call. No new callers are permitted — all production callers already use `merge_chunks_to_spool`. The function is NOT removed (backward compat) and its signature is unchanged. Any new code that calls `merge_chunks` must instead use `merge_chunks_to_spool`. | `tests/test_batch_query_engine.py::TestMergeChunks::test_merge_chunks_emits_deprecation_warning` |
| ASYNC-15 | Oracle-phase RQ concurrency cap | At most `HEAVY_QUERY_MAX_CONCURRENT` (env default 3) RQ worker functions may hold an Oracle-phase slot simultaneously across all four `execute_*_job` workers (`execute_query_tool_job`, `execute_hold_history_query_job`, `execute_resource_history_query_job`, `execute_reject_query_job`). Slot is acquired exactly once per job around the Oracle fetch only (not job-global). Exception or timeout during Oracle phase releases the slot; no slot leak. Redis unavailable: fail-open (unlimited). `execute_reject_query_job` slot is held internally by `reject_dataset_cache`; a job-level outer acquire would double-count — reject is wired at the cache layer only. Added by change `rq-semaphore-wiring`. | `tests/integration/test_rq_semaphore_wiring.py`; `tests/stress/test_rq_semaphore_stress.py` |

## Hold-History Rules

| rule id | name | current behavior | tests |
|---|---|---|---|
| HOLD-01 | Future hold cumulative decay | 「累計 Future Hold」數值邏輯正確，但 MES 釋放 lot 後會清 `FUTUREHOLDCOMMENTS`，造成歷史數值衰減 | — (known limitation) |
| HOLD-02 | Today-snapshot endpoint | `POST /api/hold-history/today-snapshot` 單次 call 返回當日 snapshot；cache namespace `hold_today:*` TTL 60s；no trend field | e2e tests |
| HOLD-03 | Duration payload shape | `duration` 結構為 `{ items: [{range, count, qty, pct}], avgReleasedHours, avgOnHoldHours, maxReleasedHours, maxOnHoldHours }` | contract tests |

## Query/Spool Rules

| rule id | name | current behavior | tests |
|---|---|---|---|
| SPOOL-01 | DuckDB spool for filtered results | 大型查詢結果存 DuckDB spool；client 透過 `query_id` / `dataset_id` 取分頁結果 | integration tests |
| SPOOL-02 | Spool expiry | Spool 過期 → 410 `CACHE_EXPIRED` 或 410 `dataset_expired`；client 必須重新觸發查詢 | resilience tests |
| SPOOL-03 | Memory pressure guard | `/api/production-history/options` 在 memory pressure 下回傳 503 | resilience tests |

## Validation Rules

| rule id | name | current behavior | tests |
|---|---|---|---|
| VAL-01 | Malicious input rejection | 所有接受查詢條件的 API 端點對惡意 payload（SQL injection、100k 字串、Unicode、倒置日期）以 `VALIDATION_ERROR` 回應而非 500 | `tests/routes/test_fuzz_routes.py` |
| VAL-02 | Required params | `POST /api/production-history/query` 缺少 `pj_types` / `start_date` / `end_date` → 400 `VALIDATION_ERROR` | route tests |
| VAL-03 | Date range validation | date range > `MAX_DATE_RANGE_DAYS` (730d) → 400 `VALIDATION_ERROR` | route tests |

## AI Query Rules

| rule id | name | current behavior |
|---|---|---|
| AI-01 | Pipeline selection | `AI_MODE` env 決定：`text2sql`（分類→SQL→執行→摘要）、`function`（combined-call function pipeline）、`agent`（多工具 agentic loop） |
| AI-02 | Clarification flag | `needs_clarification: true` 表示 AI 需要更多資訊，而非最終答案；`text2sql` / `function` mode 永遠為 `false` |
| AI-03 | Response fields | `{answer, chart_data, query_used, params_used, suggestions, sql_used, tool_trace, needs_clarification}` |
| AI-04 | Combined-prompt output schema | function mode 的 LLM call 輸出 schema：`{"function": "<name>|null", "params": {...}, "explanation": "<string>"}`；null function → null-intent path（`query_used=null`，`chart_data=null`） |
| AI-05 | Malformed JSON fallback | combined call 發生 malformed JSON（`_call_llm` 拋出 `RuntimeError` 或結果無 `function` key）→ 安全降級為 null-intent 回應；不拋出例外（AC-7）；`requests.Timeout`/`ConnectionError` 仍正常拋出 |
| AI-06 | chat_history append policy | 成功回答（含空結果）後 append `(user question, assistant answer)` 至 session chat_history；`TimeoutError`/`ConnectionError`/`ValueError` 時不 append |
| AI-07 | chat_history cap and eviction | 每個 conversation_id 最多保存 8 對/16 訊息；超過上限時以 FIFO 刪除最舊的一對（2 訊息） |
| AI-08 | History injection ordering | messages = `[system(combined prompt), ...chat_history..., user(current question)]`；history 僅注入 combined call 與 text2sql Stage 1；不注入 text2sql Stage 2（SQL 生成）或 Round 3（摘要） |
| AI-09 | Three new function behaviors | `production_history_query`：oracle/spool 同步呼叫，寬查詢可能超過 `AI_REQUEST_TIMEOUT`，建議 YAML 參數說明限制範圍不超過 7 天；`resource_history_summary`：暴露 start_date/end_date/granularity/workcenter_groups，不暴露 families/resource_ids/is_*；`qc_gate_status`：無參數，normalize_chart_data 回傳 `raw.get("stations", [])` |

## WIP Rules

| rule id | name | current behavior | tests |
|---|---|---|---|
| WIP-01 | GET/POST dual method | WIP overview 端點（`/summary`、`/matrix`、`/overview/hold`、`/detail/<workcenter>`、`/meta/filter-options`）同時接受 GET（query params）與 POST（JSON body），以避免 URL 過長 | route tests |
| WIP-02 | Matrix rate limit | `/api/wip/overview/matrix` 有 rate limit（`_WIP_MATRIX_RATE_LIMIT`）；`/api/wip/detail/<workcenter>` 有 `_WIP_DETAIL_RATE_LIMIT`；超限回 429 | route tests |
| WIP-03 | Lot detail | `GET /api/wip/lot/<lotid>` 查詢單一 lot；lotid 不存在 → 404 | route tests |
| WIP-04 | Meta endpoints | `/meta/workcenters`、`/meta/packages`、`/meta/filter-options`、`/meta/search` 提供 WIP filter 選項；均為唯讀快取查詢，不需要日期參數 | route tests |

## Hold-Overview Rules

| rule id | name | current behavior | tests |
|---|---|---|---|
| HOLD-OV-01 | Hold type filter | `reason` 參數可為 CSV string（GET）或 JSON array（POST）；`hold_type` 預設 `all` | route tests |
| HOLD-OV-02 | Hold overview endpoints | `/summary`、`/matrix`、`/treemap`、`/lots` 均接受 GET+POST；response: `success_response` with hold lot data | route tests |
| HOLD-OV-03 | Hold detail trio | `/api/wip/hold-detail/summary`、`/distribution`、`/lots` 提供 hold detail 三視角；均為同步查詢 | route tests |

## QC Gate Rules

| rule id | name | current behavior | tests |
|---|---|---|---|
| QC-01 | Cache-derived summary | `GET /api/qc-gate/summary` 從 WIP 快取衍生每站 QC-GATE lot 摘要，不直接查 DB；快取不可用 → 500 `INTERNAL_ERROR` | route tests |
| QC-02 | No filter params | QC Gate summary 無查詢參數；結果為最新快取狀態的全廠快照 | route tests |

## Resource Rules

| rule id | name | current behavior | tests |
|---|---|---|---|
| RES-01 | Resource status categories | `/by_status`、`/by_workcenter`、`/workcenter_status_matrix` 提供設備稼動率三種視角；`/status`、`/status/summary`、`/status/matrix` 提供即時設備狀態 | route tests |
| RES-02 | Detail rate limit | `POST /api/resource/detail` 有 `_RESOURCE_DETAIL_RATE_LIMIT`；`/status` 相關端點有 `_RESOURCE_STATUS_RATE_LIMIT` | route tests |
| RES-03 | NaN cleanup | resource service 對回傳數值執行 `_clean_nan_values`（NaN → null），避免 JSON 序列化失敗 | unit tests |
| RS-CF-01 | Cross-filter intersection semantics | Cross-filter selections on the resource-status page use AND-intersection semantics. Each chart (WorkcenterOuRings, OuHeatmap, MatrixSection, MaintenanceAlerts, SummaryCardGroup) contributes at most one selection dimension. The input for each chart's option rendering excludes that chart's own selection (exclude-self): selecting A narrows B but does not narrow A's own option set. Re-clicking an active selection toggles it off. ESC key clears the active selection and returns focus to the trigger element. All filtering is client-side; `/api/resource/status` payload is unchanged. | `useCrossFilter.test.ts`, `App.cross-filter.test.ts` |

## Resource History Rules

| rule id | name | current behavior | tests |
|---|---|---|---|
| RH-01 | Type A spool pattern | `POST /api/resource/history/query` → spool 存 DuckDB；view miss → 410 → client 重觸發（Type A）；response shape: `{query_id, summary, detail}` | resilience tests |
| RH-02 | Local compute flag | `RESOURCE_HISTORY_LOCAL_COMPUTE_ENABLED` env（預設 `true`）；`false` 時 `/page` endpoint 回重導向至舊路徑 | unit tests |
| RH-03 | Metadata injection | `_inject_resource_spool_info` 與 `_inject_resource_metadata` 自動將 spool info 與設備 metadata 注入 response | unit tests |
| RH-04 | Date validation | `start_date` / `end_date` 必需；無效日期格式或超過 730d → 400 `VALIDATION_ERROR` | route tests |
| RH-05 | Canonical spool key excludes granularity and filters | The canonical spool key for resource-history (`make_canonical_base_query_id` / `make_canonical_oee_query_id`) hashes only the date range and schema version — not `granularity` or any filter parameter. One parquet file serves all four granularities (day/week/month/year) and all filter combinations via DuckDB view-time bucketing and JOIN-based filtering. This is the warm-dataset key used by the warmup job (`ensure_dataset_loaded`) and the canonical read path (`try_compute_query_from_canonical_spool`). | unit + integration tests |
| RH-06 | View-result cache TTL staleness window | `apply_view()` caches the full computed result dict for `RESOURCE_VIEW_CACHE_TTL` seconds (default 300 s). Derived numbers (KPI, trend, heatmap, detail) may be up to 5 minutes stale within an already-warm dataset. This is acceptable for a reporting surface. Set `RESOURCE_VIEW_CACHE_TTL=0` to disable the cache and always recompute from spool. Cache is atomic: all structures are cached or none (no partial state). | unit tests |
| RH-07 | Spool TTL aligned to daily DuckDB refresh | The Redis spool metadata TTL for resource_history recent queries is 20h (72000 s), controlled by `RESOURCE_HISTORY_SPOOL_TTL` env var (default 72000). This is distinct from the global `CACHE_TTL_DATASET` (2h / 7200 s), which applies to hold/reject/yield_alert datasets but NOT to resource_history. Historical queries (end_date < today − 2d) continue to use `RESOURCE_HISTORY_HISTORICAL_TTL` (default 86400 s). The 20h window ensures that after the daily DuckDB prewarm refresh (keyed by `loaded_at == today`), the next user query reads newly refreshed data. | unit tests (RESOURCE_HISTORY_SPOOL_TTL resolves to 72000; CACHE_TTL_DATASET unchanged at 7200) |
| RH-08 | DuckDB prewarm via RQ job | At gunicorn startup, resource_history DuckDB prewarm is enqueued as an RQ job registered in `spool_warmup_scheduler._WARMUP_JOBS` — no `start_duckdb_prewarm()` daemon-thread call remains in `app.py`. Leader-lock (file-based `fcntl.flock`) prevents duplicate concurrent Oracle prewarms across gunicorn workers. DuckDB cache is refreshed once daily, keyed by `loaded_at == today`. If no RQ worker is available at first user query, the query falls back to Oracle without error (AC-7). | integration tests (no daemon thread on startup; RQ job enqueued; Oracle call count = 1 across N workers) |
| RH-09 | Async threshold gate | `POST /api/resource/history/query` dispatches to RQ worker when `RESOURCE_ASYNC_ENABLED=true` AND `(end_date − start_date).days ≥ RESOURCE_ASYNC_DAY_THRESHOLD` (default 90) AND `is_async_available()` returns True. Dispatched jobs return HTTP 202 `{async: true, job_id, status_url}`. Short-range queries, disabled flag, or unavailable worker fall through to the synchronous 200 path unchanged. Worker queue: `resource-history-query` (default). Job timeout: `RESOURCE_JOB_TIMEOUT_SECONDS` (default 1800 s). Spool namespace `resource_dataset` is reused (no new namespace). (resource-history-rq-async) | unit tests (AC-1, AC-2, AC-5, AC-6, AC-7); integration tests (AC-3, AC-9) |

## Production-History Rules

| rule id | name | current behavior | tests |
|---|---|---|---|
| PH-01 | Raw per-partial detail rows | Detail query draws from one raw row per LOTWIPHISTORY partial track-out in the spool. `TRACKINTIMESTAMP / TRACKOUTTIMESTAMP / TRACKINQTY / TRACKOUTQTY` are raw per-partial values in the spool — prior assumption "first partial = original batch quantity" is dropped. A view-layer aggregation (see PH-06) is applied above this row source before the API response is emitted. | unit + parity tests |
| PH-02 | Matrix lot-count semantics | Matrix `count` cell = `COUNT(DISTINCT CONTAINERNAME)` computed in DuckDB over the raw row source; equals prior aggregated-baseline lot count for the same (WC, Spec, Equipment × Month) cell. Parent-level (workcenter/spec) distinct-count rollup semantics are governed by PH-05. | integration + e2e tests |
| PH-03 | PJ_FUNCTION spool carriage | `PJ_FUNCTION` is carried through Oracle→spool→DuckDB schema and CSV export (pre-staged for Change 3); not yet exposed as a user filter | contract + parity tests |
| PH-04 | Detail row ordering | Detail table sorts by `TRACKINTIMESTAMP` ascending. For aggregated groups (PH-06), the shared `TRACKINTIMESTAMP` of the group serves as the sort key. No "partial #" column (Resolved Decision 2 of change `prod-history-detail-raw-rows`). | e2e tests |
| PH-05 | Matrix distinct-count non-additivity | Matrix tree parent-level `count` and `month_counts` (at `workcenter` and `spec` grain) are `COUNT(DISTINCT CONTAINERNAME)` re-evaluated independently at that grain — NOT the sum of child-node counts. Distinct LOT-ID counts are non-additive across the hierarchy: one CONTAINERNAME spanning multiple specs (or multiple equipment under one spec) is counted once at each ancestor node. Equipment (leaf) grain counts are unchanged (PH-02). Both code paths — DuckDB SQL (`compute_matrix_view`) and pandas fallback (`_pandas_matrix_view`) — must produce identical trees. | unit + contract + integration tests |
| PH-06 | Partial-trackout aggregation | Detail rows aggregate partial track-outs of the same upload session by the 4-tuple `(CONTAINERNAME, SPECNAME, EQUIPMENTID, TRACKINTIMESTAMP)`. The aggregated row carries `TRACKINQTY = MAX(TRACKINQTY)` (= the original load qty before any partial trackouts), `TRACKOUTTIMESTAMP = MAX(TRACKOUTTIMESTAMP)`, `TRACKOUTQTY = SUM(TRACKOUTQTY)`, and `partial_count = COUNT(*)`. TRACKINQTY is intentionally NOT a key because this MES records TRACKINQTY as the qty REMAINING at each partial's start (decreasing across partials of the same upload), not the original load. A/B-lot interleaving (same CONTAINERNAME re-entering the same EQUIPMENTID with a different TRACKINTIMESTAMP) produces distinct rows and is never merged. All production-history paths — DuckDB SQL `compute_detail_page`, pandas fallback `_pandas_detail_page`, and the CSV export stream — must apply identical aggregation logic. `pagination.total_rows` reflects the post-aggregation row count. The same 4-tuple aggregation semantics (TRACKINQTY = MAX, TRACKOUTQTY = SUM, TRACKOUTTIMESTAMP = MAX, partial_count = COUNT(*)) also apply to the three query-tool SQL files: `lot_history.sql` (4-tuple `CONTAINERID, EQUIPMENTID, SPECNAME, TRACKINTIMESTAMP`), `equipment_lots.sql` (same 4-tuple), and `adjacent_lots.sql` (3-tuple `CONTAINERID, EQUIPMENTID, TRACKINTIMESTAMP` — no SPECNAME). See QT-05. | unit + parity + contract tests |
| PH-07 | Partial-trackout strict guard | Aggregation under PH-06 collapses a group only when all non-key columns (`MFGORDERNAME`, `FIRSTNAME`, `PJ_TYPE`, `PJ_BOP`, `PJ_FUNCTION`, `PRODUCTLINENAME`, `WORKCENTERNAME`, `EQUIPMENTNAME`) are identical within the group. If any non-key column diverges across partial track-outs of the same 4-tuple, the group falls back to raw rows (no merge) for that group only; each raw row receives `partial_count = 1`. Divergence is logged at INFO level as a summary count per request (`partial-trackout strict-guard: <N> divergent groups fell back to raw rows ...`). No error is returned to the client; the raw rows remain correct data. The strict guard also applies to query-tool SQL paths (QT-06); the divergence log prefix for query-tool is `query-tool partial-trackout strict-guard: <N> divergent groups fell back to raw rows ...`. | unit tests |

## Production-History Filter Rules

| rule id | name | current behavior | tests |
|---|---|---|---|
| PHF-01 | Cross-filter cardinality | `GET /api/production-history/filter-options` 對 `selected={pj_types[], packages[], bops[], pj_functions[]}` 進行 in-memory 4-tuple 過濾（Option B）：對 `container_filter_cache.tuples` 做單次掃描，回傳「滿足當前 selected 子集」的 union of co-occurring values 給每一欄。empty `selected` → 直接回 `indices` 完整 distinct 集合（AC-1）。Cross-filter 在四個欄位之間對稱（AC-2）。 | unit + contract tests |
| PHF-02 | Wildcard grammar | 高基數欄位（`mfg_orders`, `lot_ids`, `wafer_lots`）每筆 token 規則：(1) 最多一個 `*`（任意位置：prefix/suffix/infix；多 `*` 拒絕）；(2) 純 `*` 拒絕；(3) 去除 `*` 後的 non-`*` 字元數 ≥ 2（單字元 token 拒絕；`*A*` 不可，`*AB*` 可）；(4) 多行 textarea 解析：newline / comma / whitespace 分隔，trim 後 dedup；(5) 每欄位每 request 上限 100 patterns；(6) parser idempotent：`parse(parse(x)) == parse(x)`（AC-5）。 | unit + property tests |
| PHF-03 | Wildcard SQL emit | 通過 PHF-02 的 pattern → bound parameter 形式 `col LIKE :bind ESCAPE '\'`；emit 前對 raw `%` 與 `_` 進行 escape（前綴 `\`），再將使用者的 `*` 一次性 translate 為 `%`；exact token（無 `*`）合併進 `IN (...)` batch。**禁止字串插值**；所有 binding 走 oracledb parameter style，與 `material_trace_service.py` 既有 `_add_exact_or_pattern_condition` 模式一致。 | unit + dependency-security audit |
| PHF-04 | Cache schema versioning | `container_filter_cache` payload 必含 `schema_version: int`；目前值 `2`。讀取時 schema-version mismatch → log INFO，回傳 None，強制走 Oracle 重建路徑；絕不嘗試以舊 shape 反序列化（AC-8）。Rollback 機制：bump 至 `3` 在下次 deploy 自動讓 L2 entries 失效，免去 `redis-cli DEL`。 | unit + integration tests |
| PHF-05 | Multi-worker cache rebuild lock | `container_filter_cache` 冷啟動 / TTL 過期重建使用 file-based exclusive lock：`os.open('tmp/container_filter_cache.loading', O_CREAT\|O_EXCL\|O_WRONLY)`；勝出 worker 執行 Oracle 重建後 release（`finally` 區塊保證）；其餘 workers 每 5 s 輪詢 Redis L2 共 18 次（90 s 上限），命中後 reuse；逾時 fallback 至 Oracle 重試（AC-6）。Pattern 沿用 `resource_history_duckdb_cache._try_lock/_release_lock`。 | integration + multi_worker tests |
| PHF-06 | SQL meta-char rejection | 高基數欄位 token 在進入 SQL bind 前必須通過 meta-char regex 拒絕：包含任一字元 `'`、`;`、`--`、`/*`、`*/` 或 control chars `\x00-\x1f` → 400 `VALIDATION_ERROR`，且**永不進入 Oracle**（AC-4）。Validation 集中於 `core/request_validation.py::parse_wildcard_tokens`，為高基數欄位的單一 trust boundary。 | unit + fuzz tests |
| PHF-07 | Identifier-mode date optionality | `POST /api/production-history/query` 當 request 含至少一個 identifier wildcard token（`mfg_orders` / `lot_ids` / `wafer_lots`，通過 PHF-02 解析後非空）且未提供 `start_date` / `end_date` 時，`validate_query_params` 不再要求日期，改以 wide / all-time 查詢路徑執行（identifier 述詞已充分 scope 查詢）。日期若有提供仍套用 730d 上限（VAL-03 / SYS-04）。Identifier-mode 查詢不要求 `pj_types`。（AC-4） | unit + contract + integration tests |
| PHF-08 | Classification-mode required params | `POST /api/production-history/query` 當 request 不含任何 identifier wildcard token 時為 classification mode：`pj_types`、`start_date`、`end_date` 皆為必填，缺少任一 → 400 `VALIDATION_ERROR`（行為與 prod-history-query-mode-tabs 之前完全一致，為 VAL-02 在 mode-split 後的精確化表述）。（AC-2、AC-7） | unit + contract + route tests |

## Production-Achievement Rules

| rule id | name | current behavior | tests |
|---|---|---|---|
| PA-01 | SHIFT_CODE classification (two-shift current regime) | For `TRACKOUTTIMESTAMP` where `TO_CHAR(ts,'YYYYMMDD') <= '20191231'` OR `TO_CHAR(ts,'YYYYMMDD') >= '20200330'` (i.e. all dates except the historical 2020/01/01–2020/03/29 window), shift is computed from time-of-day only: `00:00:00–07:29:59` → `N`; `07:30:00–19:29:59` → `D`; `19:30:00–23:59:59` → `N`. This is the current production regime and applies to all data outside the historical three-shift window. Re-implements Oracle function `PJ_GET_CLASSCODE_F(P_TIMESTAMP)` (not previously implemented in this codebase) in Python/SQL. Boundary seconds (07:29:59/07:30:00/19:29:59/19:30:00) are exact cutover points — no gap, no overlap. | unit tests (boundary-second assertions) |
| PA-02 | SHIFT_CODE classification (three-shift historical regime) | For `TRACKOUTTIMESTAMP` where `TO_CHAR(ts,'YYYYMMDD')` is strictly between `20191231` and `20200330` (i.e. the historical window `2020/01/01`–`2020/03/29` inclusive), shift is computed as: `08:00:00–15:59:59` → `A`; `16:00:00–23:59:59` → `B`; `00:00:00–07:59:59` → `C`. This regime is no longer in production use and exists only for correct interpretation of historical data queried within that date window. | unit tests (boundary-second assertions) |
| PA-03 | output_date cross-night attribution (two-shift current regime) | `output_date` for a given `TRACKOUTTIMESTAMP` defaults to `TRUNC(TRACKOUTTIMESTAMP)` (the calendar date), EXCEPT: for the two-shift regime (PA-01 date range), the early-morning portion of the overnight N shift — `00:00:00–07:29:59` — attributes to the PREVIOUS calendar day: `output_date = TRUNC(TRACKOUTTIMESTAMP) - 1`. Rationale: this window is the tail end of the N shift that began the prior evening (19:30:00 onward); the trackout calendar date has already rolled over but the shift instance has not. Confirmed example: 4/26 19:30–4/27 07:29 is entirely N-shift, output_date=4/26 for the whole span (including the 4/27 00:00–07:29 portion). Re-implements Oracle function `PJ_GET_OUTPUTDATE_F(TRACKOUTTIMESTAMP)`. All other two-shift time bands (`07:30:00–23:59:59`) use `output_date = TRUNC(TRACKOUTTIMESTAMP)` unchanged. | unit tests (boundary-second + cross-midnight case 4/26→4/27) |
| PA-04 | output_date cross-night attribution (three-shift historical regime) — **UNVERIFIED ASSUMPTION** | For the three-shift historical regime (PA-02 date range, 2020/01/01–2020/03/29 only): by analogy to PA-03, the C-shift early-morning band `00:00:00–07:59:59` is ASSUMED to attribute to the previous calendar day (`output_date = TRUNC(TRACKOUTTIMESTAMP) - 1`); all other three-shift bands (`08:00:00–23:59:59`) use `output_date = TRUNC(TRACKOUTTIMESTAMP)`. **This rule is NOT confirmed by the business owner** — it is inferred from the two-shift pattern (PA-03) under the assumption that C mirrors N's structural role as the shift spanning midnight. Not in scope for this change's acceptance criteria; do not treat as verified until a domain expert confirms it against real 2020 Q1 historical data. Any code path implementing this MUST log or flag three-shift-regime queries as using an unverified rule. | unit tests (documents the assumption; no production data verification performed) |
| PA-05 | Effective-output station/process qualifying predicate | A `DW_MES_LOTWIPHISTORY` (aliased `weh`) trackout row counts as production output ("有效產出") only when it satisfies the compound predicate below (in addition to the existing `CONTAINERNAME` prefix filter, which is a caller-supplied optional param, not part of the qualifying condition itself). The predicate combines `WC.SPECNAME` (station spec name), `WB.WORKFLOWNAME` (雙晶/三晶 workflow classification), and `weh.processtypename` (process type), and MUST be preserved verbatim in the achievement-rate service query — this is not a simplifiable filter: `(CASE WHEN (WB.WORKFLOWNAME LIKE '%雙晶%' OR WB.WORKFLOWNAME LIKE '%三晶%') THEN 1 ELSE 0 END = 0 AND WC.SPECNAME IN ('Epoxy D/B','Eutectic D/B','Solder Paste D/B','Solder D/B+E-Clip+固化','Solder D/B+E-Clip+固化-DW','Solder Paste D/B+E-Clip','Solder Paste D/B+E-Clip-DW')) OR WC.SPECNAME IN ('金線製程','銀線製程','銅線製程','手工跳線','雷射焊接','Eutectic D/B+Ag Wire','Eutectic D/B+Au Wire','Eutectic D/B+Cu Wire','E-Clip+固化','包膠-WB') OR (WC.SPECNAME IN ('2DB2WB','1DB2WB') AND weh.processtypename IN ('DWB_WB2')) OR (WC.SPECNAME IN ('2DB1WB','1DB1WB') AND weh.processtypename IN ('DWB_WB')) OR (WB.WORKFLOWNAME LIKE '%雙晶%' AND WC.SPECNAME IN ('Epoxy D/B-2','Eutectic D/B-2','Eutectic D/B-雙晶')) OR (WB.WORKFLOWNAME LIKE '%三晶%' AND WC.SPECNAME IN ('Epoxy D/B-3','Eutectic D/B-3')) OR (WC.SPECNAME IN ('2DB') AND weh.processtypename IN ('2DB_DB2')) OR (WC.SPECNAME IN ('1DB') AND weh.processtypename IN ('2DB_DB')) OR (WC.SPECNAME IN ('DBCB') AND weh.processtypename IN ('DBCB_CB')) OR (WC.SPECNAME IN ('2DBCBRO','1DBCBRO','CBRO') AND weh.processtypename IN ('CBA_RO'))`. Any row not matching this predicate is excluded from `SUM(TRACKOUTQTY)` and does not contribute to the achievement-rate numerator. `TRACKOUTQTY` is used directly (no `TRACKINPROCESSSPLITQTY` compensation — DWDB source is already integrated). | unit tests (predicate branch coverage: 雙晶 exclusion clause, 三晶 exclusion clause, each SPECNAME/processtypename pairing) |
| PA-06 | Achievement-rate grouping and formula | Actual output is `SUM(TRACKOUTQTY)` over PA-05-qualifying rows, grouped by `(output_date, shift_code, workcenter_group)`. `workcenter_group` is resolved via the existing `services/filter_cache.get_spec_workcenter_mapping()` (`SPECNAME → {workcenter, group, sequence}`, backed by `DW_MES_SPEC_WORKCENTER_V` / `FILTER_CACHE_SPEC_WORKCENTER_VIEW`) — the `group` field (`WORK_CENTER_GROUP`) is the 大站點/PACKAGE dimension. No new SPECNAME→station mapping is hardcoded. `achievement_rate = actual_output_qty / target_qty`. Target qty is read from the new target-value table (data-shape-contract.md §3.26), keyed by `(shift_code, workcenter_group)` only — no date dimension (same target value reused for every output_date in range). A `SPECNAME` that has no entry in `get_spec_workcenter_mapping()` is excluded from grouped output (unmapped station — cannot be assigned a 大站點/PACKAGE bucket); this is a data-boundary condition, not an error. | unit tests (grouping correctness, missing-target-row division semantics, unmapped-SPECNAME exclusion) |
| PA-07 | Achievement-rate division-by-zero / missing-target semantics | When no target-value row exists for a `(shift_code, workcenter_group)` combination present in the actual-output grouping, `achievement_rate` for that group is `null` (displayed as "—" in the UI), never `0`, `Infinity`, or a raised error. When `target_qty = 0` explicitly (a stored zero target, distinct from a missing row) and `actual_output_qty > 0`, `achievement_rate` is also `null` (division-by-zero guard; do not emit `Infinity`). When both `actual_output_qty = 0` and a non-null `target_qty > 0` exist, `achievement_rate = 0.0` (a real, displayable 0% achievement). | unit tests (missing-target null, zero-target null, zero-output-nonzero-target = 0.0) |

## Yield Alert Rules

| rule id | name | current behavior | tests |
|---|---|---|---|
| YA-01 | Process-type scope | `POST /api/yield-alert/query` accepts optional `process_type` field — closed enum `{"GA%","GC%","GD%","F%","W%","D%"}`, default `"GA%"`. Applied as `WIP_ENTITY_NAME LIKE process_type` at Oracle query time. All downstream views (trend, summary, heatmap, alerts) are scoped to the same process type via the spool. `process_type` is also one of the `query_id` hash inputs — each value produces its own spool file, so switching values never reuses another value's cached data. Omitting `process_type` defaults to `"GA%"` (backward-compatible). Any value not in the enum → 400 `VALIDATION_ERROR`. | route tests |
| YA-02 | process_type → WIP_ENTITY_NAME prefix → WIP_CLASS_CODE mapping | Verified by direct Oracle query against `DWH.ERP_WIP_MOVETXN` (6-month sample, near-exhaustive prefix census): `WIP_ENTITY_NAME` has exactly 8 observed 2-char prefixes (`GA`, `GC`, `GD`, `F2`, `FA`, `FB`, `D2`, `W2`), collapsing to 4 leading letters (`G`, `F`, `D`, `W`). Mapping: `GA%`→量產 (majority) + 9 minor `WIP_CLASS_CODE` values (see YA-02a); `GC%`→點測 (100%); `GD%`→重工RW (100%); `F%` (covers `F2`/`FA`/`FB`)→委外 (100%); `W%` (covers `W2`)→量產 (390 rows) + PJ_NST_A (9 rows); `D%` (covers `D2`)→PJ_NST_A (100%). The 6 LIKE patterns are mutually exclusive by construction (disjoint leading-character sets: `GA%`/`GC%`/`GD%` are 2-char-exact prefixes under the shared `G` letter and do not overlap each other; `F%`, `W%`, `D%` are single-leading-letter patterns disjoint from `G%` and from each other). A future `WIP_ENTITY_NAME` prefix outside these 8 (e.g. a hypothetical new `GB%`) would match none of the 6 options and remain invisible — not silently miscounted into an existing bucket. | unit tests (query_id hash + LIKE-pattern disjointness assertions) |
| YA-02a | GA% is not sub-split by WIP_CLASS_CODE | GA% remains a single `process_type` option despite internally covering 10 distinct `WIP_CLASS_CODE` values (量產, 代工, 樣品, 工程, 餘晶, 已驗證, 久存, WIP, 試量產, 打帶跑 — 量產 is the overwhelming majority). This change does not split GA% further; a future change may. | n/a (non-goal, documented for traceability) |
| YA-03 | PACKAGE IS NOT NULL filter removal | The `PACKAGE IS NOT NULL` predicate is removed from all GA% queries. Rationale: verified by direct Oracle query — zero GA% workorder rows have PACKAGE=NA. The filter was redundant and added unnecessary exclusion risk. For GC%, PACKAGE=NA is valid data and must never be filtered. | data-invariant test |
| YA-04 | SOURCE_CODE NOT NULL ⇒ TX_QTY=0 | When `ERP_WIP_MOVETXN_DETAIL.SOURCE_CODE IS NOT NULL`, the row is a LOT-level scrap attribution row and its `TRANSACTION_QTY` (TX) is always 0. Verified by direct Oracle query: 100% of SOURCE_CODE NOT NULL rows have TX=0. These rows MUST NOT be summed into the TX denominator. The yield formula (`SCRAP_QTY / TX_QTY`) at workorder grain is unchanged. | unit tests (data-invariant assertion) |
| YA-05 | LOT dimension in alert list | The alert list (`GET /api/yield-alert/alerts`) exposes `source_code: string \| null` per row. Non-null `source_code` identifies the LOT ID (`DW_MES_WIP.CONTAINERNAME` equivalent) responsible for the scrap. This adds display precision without changing alert-level scrap totals or yield thresholds. Alert triggering logic operates on workorder-grain aggregates that exclude TX=0 rows (YA-04). | route + unit tests |
| YA-06 | Spool-first view serving | All four yield-alert views (trend, summary, heatmap, alerts) are computed from the `yield_alert_dataset` DuckDB spool after the initial query. No separate Oracle trend.sql or summary.sql query is issued for view serving. A spool miss → 410 `CACHE_EXPIRED`; client must re-trigger `POST /api/yield-alert/query` (Type A pattern, same as hold-history). The live-query fallback path is retired. | resilience tests |
| YA-07 | Reject linkage in single spool pull | The `REJECT_LINKED` boolean flag for each spool row is computed during the initial Oracle pull (by joining against the reject table in the same query). The prior separate `_compute_reject_linkage` Oracle query after the main pull is retired. | unit + integration tests |
| YA-08 | ERP_WIP_MOVETXN_DETAIL as data source | Trend and summary aggregations use `ERP_WIP_MOVETXN_DETAIL` (row-level detail table) instead of `ERP_WIP_MOVETXN` (pre-aggregated). Verified by direct Oracle comparison: GA% totals identical (TX=70,494,377, SCRAP=81,972). `ERP_WIP_MOVETXN_DETAIL` provides `SOURCE_CODE` (LOT ID) which the aggregate table does not. | parity test (totals match) |
| YA-09 | Spool schema version | `yield_alert_dataset_cache.py` contains a `_SCHEMA_VERSION` integer constant that participates in the spool cache key. Bumping `_SCHEMA_VERSION` orphans stale parquets by key without requiring a manual `rm`. Any column add/remove/rename MUST bump `_SCHEMA_VERSION` in the same commit. Schema-breaking rollback also requires: `rm -f tmp/query_spool/yield_alert_dataset/*.parquet`. | env-validation / constant-pin test |
| YA-10 | workcenter_groups computed from spool, not global cache | For `GET /api/yield-alert/view` and `GET /api/yield-alert/cross-filter-options` ONLY, `workcenter_groups` is computed as `SELECT DISTINCT DEPARTMENT_NAME` against the `query_id` spool — the same mechanism already used for `lines`/`packages`/`types`/`functions`/`process_categories`. It no longer reads the global `filter_cache.get_workcenter_groups()` (`DWH.DW_MES_SPEC_WORKCENTER_V`) or applies the `_YIELD_WORKCENTER_GROUP_ORDER`/`_DEPT_SEQ_MAP` grouping/ordering layer for this page. The source column is `DEPARTMENT_NAME` (raw, trimmed-only) — explicitly not `DEPARTMENT_GROUP` (the normalized column `_normalize_yield_department_group()` produces for heatmap/station_summary aggregation elsewhere in this module). | integration tests (spool-derived, cross-filter narrowing) |
| YA-11 | Shared filter_cache path unaffected | `GET /api/yield-alert/filter-options` (the initial-load dropdown-seed endpoint) and every other page/consumer of `filter_cache.get_workcenter_groups()` are unchanged by YA-10 — this rule re-points only the two yield-alert-center endpoints named above, not the shared cache itself. | regression test (other filter_cache consumers unaffected) |
| YA-12 | workcenter_groups empty-spool behavior | When the `query_id` spool has zero rows for the current filter selection (e.g. a new `process_type` value with no matching data yet), `workcenter_groups` returns an empty array — not an error — consistent with the empty-result handling of the other filter dimensions (YA-01/YA-02 new process_type values must not 500 on zero rows). | data-boundary test |
| YA-13 | KPI summary scope = alert-candidate scope + tx-dedup | `GET /api/yield-alert/view` (`data.summary`) and `GET /api/yield-alert/summary` — `summary.transaction_qty`/`summary.scrap_qty` are computed over the SAME row set as the alert-candidate list (`_query_alerts()` in `yield_alert_sql_runtime.py`), not the broader scope `_query_summary()` previously used (all 6 dimension filters were already applied there, but it omitted the alert-candidate predicate). Predicate: `SCRAP_QTY <> 0 AND NOT (yield_pct >= risk_threshold AND scrap_qty < min_scrap_qty)`, with all 6 dimension filters (departments, process_category, lines, packages, types, functions). Both endpoints must receive `risk_threshold`/`min_scrap_qty` — `GET /api/yield-alert/summary` previously dropped these params and must forward them. `scrap_qty` is a plain `SUM` over alert-candidate rows (already grouped per `REASON_CODE`, no fan-out). `transaction_qty` MUST be deduped before summing on `_query_alerts()`'s local `tx_extra_cols` key (`WORKORDER`, `DEPARTMENT_GROUP`, `PROCESS_CATEGORY`, `LINE_NAME`, `PACKAGE_NAME`, `TYPE_NAME`, `FUNCTION_NAME`, `OPERATION_TEXT`, plus the bucketed `DATE_BUCKET`) — NOT the module-level `_TX_DEDUP_COLS` constant used by trend/heatmap/station/package summary, which additionally includes raw `DEPARTMENT_NAME` and is too fine a key for the `tx_lookup` CTE this KPI reuses; using the wrong key silently breaks the double-count fix. An alert-candidate group spanning multiple distinct `REASON_CODE` rows for one (workorder+date+dept+...) tuple must contribute its `transaction_qty` exactly once. Scope boundary: this rule applies to the top-level KPI summary only — `trend`/`heatmap`/`station_summary`/`package_summary` intentionally keep their prior (broader, non-threshold) scope, documented as a non-goal. | unit + integration tests (KPI↔CSV reconciliation, multi-reason_code double-count regression) |

## Reject-History Prefilter Rules

| rule id | name | current behavior | tests |
|---|---|---|---|
| RHPF-01 | BASE_WHERE injection | `pj_types`, `packages`, `pj_functions`, and `reasons` prefilter conditions are injected into `{{ BASE_WHERE }}` inside the `reject_raw` CTE of `performance_daily_lot.sql`, BEFORE the GROUP BY clause. The supplementary `{{ WHERE_CLAUSE }}` layer (workcenter_groups, packages, reasons, types) is fully removed by change `rh-remove-supplementary-filter`. | unit tests |
| RHPF-02 | Empty selection = no restriction | When any of the four prefilter fields is absent from the request body OR is an empty array, no SQL condition is added for that field. Results are identical to current behavior (backward-compatible). | unit + route tests |
| RHPF-03 | NVL/TRIM NULL-container sentinel | Prefilter SQL conditions for container-level fields use `NVL(TRIM(c.PJ_TYPE/PRODUCTLINENAME/PJ_FUNCTION), '(NA)') IN (:bind_list)`. Oracle NULL values (rows whose container is absent from DW_MES_CONTAINER) map to the sentinel string `(NA)` and are NOT silently dropped. Selecting `(NA)` explicitly returns NULL-container rows. | unit + data-boundary tests |
| RHPF-04 | PJ_BOP explicitly excluded | `performance_daily_lot.sql` does not JOIN or SELECT `PJ_BOP`. No `pj_bop` request parameter, no SQL clause, no UI control is added by this change. Requests containing `pj_bop` must silently ignore it. | unit tests |
| RHPF-05 | Sync/async parity | The four prefilter fields (`pj_types`, `packages`, `pj_functions`, `reasons`) must be forwarded identically in both the sync (HTTP 200 fallback) and async/RQ (HTTP 202) job paths. Spool/cache keys for the `reject_dataset` namespace must incorporate all four fields to prevent cross-query cache collisions. | unit + integration tests |
| RHPF-06 | Options from shared container_filter_cache | Filter option values for `pj_types`, `packages`, and `pj_functions` are sourced from the existing `container_filter_cache` 4-tuple set (same backing store used by `GET /api/production-history/filter-options`). No new cache namespace, no new Oracle query path, no modification to the shared producer. | unit tests |
| RHPF-07 | NVL/TRIM NULL-LOSSREASONNAME sentinel | `reasons[]` prefilter uses `NVL(TRIM(r.LOSSREASONNAME), '(未填寫)') IN (:bind_list)`. Source is `LOTREJECTHISTORY.LOSSREASONNAME` (direct column, not a LEFT JOIN miss). Sentinel `(未填寫)` is distinct from `(NA)` used for container-level fields. Selecting `(未填寫)` returns reject records where LOSSREASONNAME is null or blank. Options sourced from `GET /api/reject-history/options` via `reason_filter_cache.get_reject_reasons()`. | unit + data-boundary tests |
| RHPF-08 | WHERE-semantics equivalence | The BASE_WHERE `reasons[]` prefilter produces result sets equivalent to the prior supplementary DuckDB-layer reason filter for the same selection, including the `(未填寫)` bucket. Equivalence holds because NVL/TRIM at Oracle layer maps null rows identically to `(未填寫)` as the prior DuckDB filter did. AC-7. | data-boundary tests |


## Analytics / Anomaly Detection Rules

| rule id | name | current behavior | tests |
|---|---|---|---|
| ANA-01 | Cache-only response | Analytics 端點（`/anomaly-summary`、`/yield-anomalies`、`/reject-spikes`、`/hold-outliers`、`/equipment-deviation`）從 Redis 快取讀取排程計算結果；不直接查 DB | route tests |
| ANA-02 | Feature flag gate | `ANALYTICS_ANOMALY_DETECTION_ENABLED` 控制；disabled → 所有 analytics 端點回 503 `SERVICE_UNAVAILABLE` | unit tests |
| ANA-03 | Cache state meta | `/anomaly-summary` 在 response `meta` 注入 `cache_state ∈ {warm, cold, stale}`；`cold` 表示尚無排程結果 | route tests |
| ANA-04 | Drilldown spool | `*/drilldown` 端點從異常偵測 spool 讀取，不走 Oracle；spool 過期 → 410 | resilience tests |

## Query Tool Rules

| rule id | name | current behavior | tests |
|---|---|---|---|
| QT-01 | Lot resolution | `POST /api/query-tool/resolve` 接受 lot ID 或 container ID，回傳 normalized lot list；multi-lot 批次超限 → 400 `VALIDATION_ERROR` | route tests |
| QT-02 | Batch size limit | `_query_tool_max_container_ids()` 讀自 env；批次 container_ids 超限 → 400（`_reject_if_batch_too_large`）| route tests |
| QT-03 | Export format | `POST /api/query-tool/export-csv` 支援多視角（materials、holds、equipment lots、history、rejects、jobs）；`_format_*_export_rows` 函式群各自轉換欄位 | e2e tests |
| QT-04 | Equipment lookup | `POST /api/query-tool/lot-equipment-lookup` 接受多 lot；`GET /equipment-recent-jobs/<equipment_id>` 查單設備近期 jobs | route tests |
| QT-05 | Partial-trackout aggregation (query-tool) | `lot_history.sql` and `equipment_lots.sql` aggregate partial track-outs by the 4-tuple `(CONTAINERID, EQUIPMENTID, SPECNAME, TRACKINTIMESTAMP)`. `adjacent_lots.sql` uses a 3-tuple `(CONTAINERID, EQUIPMENTID, TRACKINTIMESTAMP)` (SPECNAME not in adjacent-lots scope). All three: `TRACKINQTY = MAX(TRACKINQTY)` (original load qty — MES stores REMAINING qty which decreases across partials), `TRACKOUTQTY = SUM(TRACKOUTQTY)`, `TRACKOUTTIMESTAMP = MAX(TRACKOUTTIMESTAMP)`, `partial_count = COUNT(*)`. Prior `ROW_NUMBER() OVER (...ORDER BY TRACKOUTTIMESTAMP DESC) WHERE rn=1` returned only the last partial's TRACKINQTY (lowest remaining qty) and TRACKOUTQTY (one partial only) — a silent data-accuracy bug. `partial_count` is an additive output column; existing consumers that ignore unknown columns are unaffected. | unit + contract tests |
| QT-06 | Partial-trackout strict guard (query-tool) | Mirrors PH-07 for query-tool SQL paths. A group collapses only when all non-key columns are identical across its partials. For `lot_history.sql` / `equipment_lots.sql` the non-key columns are: `WORKCENTERNAME, EQUIPMENTNAME, FINISHEDRUNCARD, PJ_WORKORDER, CONTAINERNAME, PJ_TYPE, PJ_BOP, WAFER_LOT_ID`. For `adjacent_lots.sql`: `EQUIPMENTNAME, SPECNAME, FINISHEDRUNCARD, PJ_WORKORDER, CONTAINERNAME, PJ_TYPE, PJ_BOP, WAFER_LOT_ID`. If any non-key column diverges, the group falls back to raw rows with `partial_count = 1` each. Divergence logged at INFO level per request (`query-tool partial-trackout strict-guard: <N> divergent groups fell back to raw rows ...`). No error returned to client. | unit tests |
| QT-07 | Equipment-rejects cross-station semantic | `get_equipment_rejects()` resolves the queried EQUIPMENTIDs against `LOTWIPHISTORY` (`TRACKINTIMESTAMP` within window) to a DISTINCT CONTAINERID set, then returns `LOTREJECTHISTORY` rows for those CONTAINERIDs. The reject event's EQUIPMENTNAME may differ from the queried equipment (cross-station case: a lot processed on Furnace-A may have its reject event logged under Furnace-B — intentional, not a bug). `LOTREJECTHISTORY` has no EQUIPMENTID; CONTAINERID is the only correct join key. Empty equipment_ids → `UserInputError` (AC-4 short-circuit; LOTREJECTHISTORY query never executed). Implemented in `equipment_lot_rejects.sql` + `get_equipment_rejects()`. | `TestGetEquipmentRejects` |

## Job Query Rules

| rule id | name | current behavior | tests |
|---|---|---|---|
| JQ-01 | Job resources | `GET /api/job-query/resources` 回傳可查詢的 job 類型清單（workcenter、layer 等分類）| route tests |
| JQ-02 | Job history query | `POST /api/job-query/jobs` 接受過濾條件（resource、date range、status）；結果同步回傳 | route tests |
| JQ-03 | Transaction history | `GET /api/job-query/txn/<job_id>` 查單 job 的 transaction 歷史；不存在 → 404 | route tests |
| JQ-04 | CSV export | `POST /api/job-query/export` 以 CSV stream 回傳 job 清單；stream-download-exception 端點 | e2e tests |

## Dashboard Rules

| rule id | name | current behavior | tests |
|---|---|---|---|
| DASH-01 | KPI aggregation | `POST /api/dashboard/kpi` 聚合廠區 KPI（WIP count、hold rate、yield）；資料來自快取；POST JSON body 含 filter 條件 | route tests |
| DASH-02 | Workcenter cards | `POST /api/dashboard/workcenter_cards` 回傳每個 workcenter 的 status card；結構固定 | route tests |
| DASH-03 | OU trend | `POST /api/dashboard/ou_trend` 回傳 OU（Operating Unit）趨勢時序資料 | route tests |
| DASH-04 | Utilization heatmap | `POST /api/dashboard/utilization_heatmap` 回傳設備稼動率熱力圖矩陣；`NaN` 值在 service 層清除 | route tests |

## Mid-Section Defect Rules

| rule id | name | current behavior | tests |
|---|---|---|---|
| MSD-01 | Compatibility adapter | `mid_section_defect_routes.py` 是 trace 資料的 compatibility adapter；`/analysis` 接受可選 `trace_query_id`（已有 spool 可跳過重查）| route tests |
| MSD-02 | Cache key | Analysis cache key 由 `_analysis_cache_key()` 生成（包含所有 filter params）；cache miss → 查詢 Oracle/DuckDB | route tests |
| MSD-03 | Station options | `GET /api/mid-section-defect/station-options` 提供站點 filter 清單；`/loss-reasons` 提供 loss reason 清單 | route tests |
| MSD-04 | CSV export | `GET /api/mid-section-defect/export` stream-download-exception；content-type: text/csv | e2e tests |
| MSD-05 | container-filter-options no-Oracle invariant | `GET /api/mid-section-defect/container-filter-options` reads from `container_filter_cache` only (24h TTL); no Oracle query is issued at request time. A cold or fully-expired cache returns HTTP 200 with all four arrays empty; the client must tolerate empty lists. Analogous to RHPF-06 for reject-history. | `tests/e2e/test_mid_section_defect_e2e.py::TestMidSectionDefectE2E::test_container_filter_options_uses_cache_not_oracle` |
| MSD-06 | Forward Top-N truncation | `by_detection_loss_reason` and the crosstab loss_reason axis are independently truncated to TOP_N=10; rows beyond TOP_N are folded into a synthetic "其他" row. The downstream-workcenter axis is also TOP_N=10 independently. Sankey drops self-zero links. TOP_N is a constant, not a query param. | `tests/test_mid_section_defect_service.py::test_by_detection_loss_reason_top_n_truncation`, `test_crosstab_top_n_folds_remainder_to_other` |
| MSD-07 | Amplification KPI semantics | amplification = downstream_reject_rate ÷ detection_reject_rate over the SAME SEED_ID flagged cohort; within-cohort ratio, NOT flagged-vs-clean lift. **Decision table:** detection_rate=0 → null (display "—", never ∞ or sentinel); downstream=0 & detection>0 → 0.0; both>0 → downstream_rate/detection_rate. | `tests/test_mid_section_defect_service.py::test_amplification_kpi_*` |
| MSD-08 | Forward lineage attribution | `_attribute_forward_defects` re-keys descendant rejects to SEED_ID via lineage spool JOIN when `lineage_spool_df` is provided; split/merge/rename descendants are included. genealogy_status="error" → self-edge-only graceful degrade (never 5xx). get_summary(direction="forward") always via DuckDB; in-memory forward summary path retired. | `tests/test_mid_section_defect_service.py::test_attribute_forward_defects_lineage_rekeying_passes`, `tests/test_unified_spool_integration.py::TestMsdFullChain` |
| MSD-09 | Front×downstream reason correlation matrix | `_build_front_downstream_reason_matrix` attributes each downstream reject (re-keyed to SEED_ID via lineage) to EVERY front-stage loss reason its seed carries — **cohort membership**, so a lot with multiple front reasons counts in multiple rows and Σcells may exceed the physical reject total. Rows/cols independently TOP_N=10 + "其他"; `row_pct` row-normalized to 100% (0.0 when row total=0) is the primary display. Empty → `{rows:[],cols:[],cells:[],row_pct:[]}`. | `tests/test_mid_section_defect_service.py::TestFrontDownstreamReasonMatrix` |
| MSD-10 | Detection input qty = session original load | Detection `偵測投入` (TRACKINQTY emitted by `station_detection_by_ids.sql`) must be `MAX(TRACKINQTY) OVER (PARTITION BY CONTAINERID, TRACKINTIMESTAMP, EQUIPMENTID)` — the upload session's original load — NOT the last partial's remaining qty. Per PH-06 TRACKINQTY decrements across partials; picking rn=1 under-counts input and inflates downstream/defect rates past 100%. Applies to BOTH forward and backward (shared SQL/spool). | `tests/test_mid_section_defect_service.py::TestDetectionInputPartialAggregation` |
| MSD-11 | Backward upstream attribution must not fan-out defect_qty | The DuckDB backward attribution charts (`by_machine`, `by_material`, raw machine/materials attribution, `by_wafer_root` fallback) JOIN `defective_kpis × lineage × events`; summing `dk.defect_qty`/`dk.trackin_qty` directly over that join counts each defect lot once per matching upstream EVENT row, so a single dimension can exceed the cohort total (observed: one machine 不良數 366 > 不良總數 252). Invariant: **no single attribution dimension may exceed the cohort total defect_qty**. Implementation must collapse the lineage×events fan-out to one row per `(dimension, CONTAINERID)` via `SELECT DISTINCT` BEFORE aggregating (then `COUNT(*)`/`SUM`); label-only columns (e.g. material description) are computed in a separate CTE so they never enter the dedup key. Mirrors the in-memory `_attribute_defects` (a SET per dimension), which never had the bug. | `tests/test_msd_duckdb_runtime.py::TestBackwardAttributionNoFanout` |

## Admin Rules

| rule id | name | current behavior | tests |
|---|---|---|---|
| ADMIN-01 | Double auth gate | Admin 端點需同時通過 `login_required` + `is_admin` check；缺少任一 → 403 `FORBIDDEN` | route tests |
| ADMIN-02 | Performance metrics | `/admin/api/performance-history` 儲存 API response time 歷史；`/purge` 清空；`/detail` 查詢單次請求詳情 | route tests |
| ADMIN-03 | Worker management | `POST /admin/api/worker/restart` 重啟 RQ worker；`GET /worker/status` 查 worker 狀態；需 admin | route tests |
| ADMIN-04 | Drawer CRUD | `/admin/api/drawers` 管理導覽欄 drawer 設定；支援 CRUD（GET/POST/PUT/DELETE）| route tests |
| ADMIN-05 | Log management | `/admin/api/logs`、`/logs/cleanup`、`/log-files/cleanup` 管理系統 log；cleanup 用 DELETE method | route tests |
| ADMIN-06 | Log query path divergence | `query_logs_all()` and `count_logs()` in `log_store.py` MUST NOT filter by `synced`; they return all records (synced and unsynced) for the admin view. `query_logs()` (legacy consumer path) intentionally retains `WHERE synced = 0`. Adding a `synced` filter to the "all" variants silently hides records from `/admin/api/logs`. Retention window: synced records are purged after 24 h (`older_than_hours=24`) by `SyncWorker._cleanup_synced()`. | `tests/test_log_store.py::TestLogStoreAllRows` |
| ADMIN-07 | Log pagination authoritative total | For `/admin/api/logs`, `total` in the pagination meta MUST be computed from independent `COUNT` queries (`log_store.count_logs()` + `_count_mysql_logs()`) executed without the page window — NOT from `len(merged_rows)` after a windowed fetch. The windowed fetch uses `limit = offset + page_size` per source to cover the merge sort window; post-merge slice is `rows[offset : offset + page_size]`. Deriving `total` from a windowed fetch silently under-counts when `offset > 0`. | `tests/test_admin_routes_logs.py::TestMergePagination` |

## Decision Tables

| condition | behavior | rule | test id |
|---|---|---|---|
| RQ worker available + spool miss | HTTP 202 async job | ASYNC-02 | — |
| RQ worker unavailable + spool miss | HTTP 200 sync fallback | ASYNC-02 | resilience |
| Spool hit | HTTP 200 直接回傳 | SPOOL-01 | — |
| Spool expired | HTTP 410 `CACHE_EXPIRED` / `dataset_expired` | SPOOL-02 | resilience |
| DB unavailable | HTTP 503 `service_unavailable` | SYS-01 | resilience |
| Malicious input | HTTP 400 `VALIDATION_ERROR` | VAL-01 | fuzz tests |
| Date range > 730d | HTTP 400 `VALIDATION_ERROR` | VAL-03 | route tests |
| Identifier token present + no dates | wide / all-time query, no dates-required error | PHF-07 | contract + integration |
| No identifier token + missing pj_types/dates | HTTP 400 `VALIDATION_ERROR` | PHF-08 | route tests |
| Partial trackout group — 4-tuple match, non-key columns consistent | Single aggregated row; `trackin_qty = MAX(...)` (original load), `trackout_qty = SUM(...)`, `trackout_time = MAX(...)`, `partial_count ≥ 2` | PH-06 | unit tests |
| Partial trackout group — 4-tuple match, any non-key column diverges | Multiple raw rows emitted, `partial_count = 1` each; per-request INFO log with divergent-group count | PH-07 | unit tests |
| Downtime query: days ≥ DOWNTIME_ASYNC_DAY_THRESHOLD + DOWNTIME_ASYNC_ENABLED=true + worker available | HTTP 202 async job | ASYNC-DA-01 | route tests |
| Downtime query: days < threshold, OR DOWNTIME_ASYNC_ENABLED=false, OR worker unavailable | HTTP 200 sync | ASYNC-DA-01 | resilience |
| Resource-history query: days ≥ RESOURCE_ASYNC_DAY_THRESHOLD + RESOURCE_ASYNC_ENABLED=true + worker available | HTTP 202 async job | RH-09 | route tests |
| Resource-history query: days < threshold, OR RESOURCE_ASYNC_ENABLED=false, OR worker unavailable | HTTP 200 sync | RH-09 | resilience |
| EAP ALARM query: `EAP_ALARM_USE_UNIFIED_JOB=on` + async available | HTTP 202 async job (EapAlarmJob) | EA-ASYNC, ASYNC-06 | route tests |
| EAP ALARM query: `EAP_ALARM_USE_UNIFIED_JOB=on` + async unavailable | HTTP 503 SERVICE_UNAVAILABLE + Retry-After | EA-ASYNC, ASYNC-06 | resilience tests |
| EAP ALARM query: `EAP_ALARM_USE_UNIFIED_JOB=off` (default) | unchanged legacy path (run_eap_alarm_query_job) | EA-ASYNC, AC-8 | regression tests |
| Production History query: `PRODUCTION_HISTORY_USE_UNIFIED_JOB=on` + async available | HTTP 202 async job (ProductionHistoryJob) | ASYNC-07 | route tests |
| Production History query: `PRODUCTION_HISTORY_USE_UNIFIED_JOB=on` + async unavailable | HTTP 503 (sync_fallback_allowed=True; no forced 503 unless enqueue fails) | ASYNC-07 | resilience tests |
| Production History query: `PRODUCTION_HISTORY_USE_UNIFIED_JOB=off` (default) | legacy path unchanged | ASYNC-07, AC-8 | regression tests |
| Reject History query: `REJECT_HISTORY_USE_UNIFIED_JOB=on` + async available | HTTP 202 async job (RejectHistoryJob) | ASYNC-07 | route tests |
| Reject History query: `REJECT_HISTORY_USE_UNIFIED_JOB=on` + async unavailable | HTTP 503 (sync_fallback_allowed=True) | ASYNC-07 | resilience tests |
| Reject History query: `REJECT_HISTORY_USE_UNIFIED_JOB=off` (default) | legacy path unchanged | ASYNC-07, AC-8 | regression tests |
| Material Trace query: `MATERIAL_TRACE_USE_UNIFIED_JOB=on` + async available | HTTP 202 async job (MaterialTraceJob, always_async=True) | ASYNC-10 | route tests |
| Material Trace query: `MATERIAL_TRACE_USE_UNIFIED_JOB=on` + async unavailable | HTTP 503 SERVICE_UNAVAILABLE + Retry-After; no sync fallback (D4) | ASYNC-10, ASYNC-06 | resilience tests |
| Material Trace query: `MATERIAL_TRACE_USE_UNIFIED_JOB=off` (default) | legacy path unchanged (_execute_batched_query_to_parquet) | ASYNC-10, AC-1 | regression tests |
| Downtime query: `DOWNTIME_USE_UNIFIED_JOB=on` + async available | HTTP 202 async job (DowntimeJob, always_async=True) | DDA-01, ASYNC-06 | route tests |
| Downtime query: `DOWNTIME_USE_UNIFIED_JOB=on` + async unavailable | HTTP 503 SERVICE_UNAVAILABLE + Retry-After; no sync fallback | DDA-01, ASYNC-06 | resilience tests |
| Downtime query: `DOWNTIME_USE_UNIFIED_JOB=off` (default) | legacy path unchanged (_bridge_jobid Path B pd.merge) | DDA-01, AC-8 | regression tests |
| N concurrent heavy RQ workers (N > HEAVY_QUERY_MAX_CONCURRENT) | Peak simultaneous Oracle-phase executions ≤ HEAVY_QUERY_MAX_CONCURRENT (default 3); all N complete; no deadlock | ASYNC-15 | stress gate (`tests/stress/test_rq_semaphore_stress.py`) |
| Oracle phase raises exception during slot hold | Slot released in finally block; subsequent job can acquire; no leak | ASYNC-15 | resilience tests (`tests/integration/test_rq_semaphore_wiring.py`) |
| Reject-history prefilter: non-empty `pj_types`/`packages`/`pj_functions` | `NVL(TRIM(c.col), '(NA)') IN (...)` injected into `{{ BASE_WHERE }}` of `reject_raw` CTE | RHPF-01, RHPF-03 | unit tests |
| Reject-history prefilter: empty list or field absent | No SQL clause added; results equivalent to omitting the filter entirely | RHPF-02 | unit + route tests |
| Reject-history prefilter: `(NA)` in selection | Returns rows where `DW_MES_CONTAINER` has no matching record (NULL container → `(NA)` sentinel matches) | RHPF-03 | data-boundary tests |
| Reject-history prefilter: `pj_bop` sent by caller | Silently ignored; no `PJ_BOP` clause added; no error | RHPF-04 | route tests |
| Reject-history `reasons[]` prefilter: non-empty | `NVL(TRIM(r.LOSSREASONNAME), '(未填寫)') IN (...)` injected into `{{ BASE_WHERE }}`; `reason_`-prefixed bind params | RHPF-01, RHPF-07 | unit tests |
| Reject-history `reasons[]` prefilter: empty list or field absent | No SQL clause added; results equivalent to omitting the filter entirely | RHPF-02 | unit + route tests |
| Reject-history `reasons[]` prefilter: `(未填寫)` in selection | Returns reject records where LOSSREASONNAME is null or blank | RHPF-07 | data-boundary tests |
| Reject-history `workcenter_groups` sent by caller | No longer accepted; silently ignored (supplementary WHERE layer removed) | RHPF-01 | route tests |
| D/B-START lot: WORKFLOWNAME match found (STATUS=ACTIVE, EQUIPMENTS NOT NULL) | One row per distinct EQUIPMENT; matchSource="workflow" | DB-02 | unit tests |
| D/B-START lot: no WORKFLOWNAME match, BOP[0]=U | Query Eutectic D/B + 1DB/2DB group; matchSource="bop-fallback" | DB-03 | unit tests |
| D/B-START lot: no WORKFLOWNAME match, BOP[0]=E | Query Epoxy D/B only; matchSource="bop-fallback" | DB-03 | unit tests |
| D/B-START lot: no WORKFLOWNAME match, BOP[0]=P | Query DBCB + Solder Paste + 錫膏網印 group; matchSource="bop-fallback" | DB-03 | unit tests |
| D/B-START lot: no WORKFLOWNAME match, BOP[0] other or BOP null | No recommendation row; matchSource="none"; no error | DB-03 | unit tests |
| `TRACKOUTTIMESTAMP` date outside 2020/01/01–2020/03/29, time 00:00:00–07:29:59 or 19:30:00–23:59:59 | `SHIFT_CODE = N` | PA-01 | unit tests |
| `TRACKOUTTIMESTAMP` date outside 2020/01/01–2020/03/29, time 07:30:00–19:29:59 | `SHIFT_CODE = D` | PA-01 | unit tests |
| `TRACKOUTTIMESTAMP` date within 2020/01/01–2020/03/29, time 08:00:00–15:59:59 | `SHIFT_CODE = A` | PA-02 | unit tests |
| `TRACKOUTTIMESTAMP` date within 2020/01/01–2020/03/29, time 16:00:00–23:59:59 | `SHIFT_CODE = B` | PA-02 | unit tests |
| `TRACKOUTTIMESTAMP` date within 2020/01/01–2020/03/29, time 00:00:00–07:59:59 | `SHIFT_CODE = C` | PA-02 | unit tests |
| Two-shift regime, time 00:00:00–07:29:59 (N-shift tail) | `output_date = TRUNC(TRACKOUTTIMESTAMP) - 1` | PA-03 | unit tests |
| Two-shift regime, time 07:30:00–23:59:59 | `output_date = TRUNC(TRACKOUTTIMESTAMP)` | PA-03 | unit tests |
| Three-shift regime, time 00:00:00–07:59:59 (C-shift tail) — UNVERIFIED | `output_date = TRUNC(TRACKOUTTIMESTAMP) - 1` (assumption) | PA-04 | unit tests (assumption documented, not production-verified) |
| Three-shift regime, time 08:00:00–23:59:59 | `output_date = TRUNC(TRACKOUTTIMESTAMP)` | PA-04 | unit tests |
| Trackout row matches PA-05 predicate | Row counts toward `SUM(TRACKOUTQTY)` for its `(output_date, shift_code, workcenter_group)` group | PA-05 | unit tests |
| Trackout row does not match PA-05 predicate | Row excluded from achievement-rate numerator entirely | PA-05 | unit tests |
| Target row missing for `(shift_code, workcenter_group)` | `achievement_rate = null` (display "—") | PA-07 | unit tests |
| Target row present with `target_qty = 0`, `actual_output_qty > 0` | `achievement_rate = null` (never Infinity) | PA-07 | unit tests |
| Target row present with `target_qty > 0`, `actual_output_qty = 0` | `achievement_rate = 0.0` | PA-07 | unit tests |

## Material Consumption Rules

| rule id | name | behavior | tests |
|---|---|---|---|
| MC-01 | Consumption data source and grouping | Reads `QTYCONSUMED` (actual) and `QTYREQUIRED` (required) from `DWH.DW_MES_LOTMATERIALSHISTORY`. Grouped by `TRUNC(TXNDATE)` (date-only; not datetime). Product type dimension joins `DWH.DW_MES_CONTAINER.PJ_TYPE`. Granularity GROUP BY (DuckDB): `week = date_trunc('week', txn_date)`, `month = strftime(txn_date, '%Y-%m')`, `quarter = CAST(YEAR(txn_date) AS VARCHAR) \|\| '-Q' \|\| CAST(QUARTER(txn_date) AS VARCHAR)`. Granularity switch re-groups summary spool in DuckDB without Oracle re-query (ADR-0001). | unit + contract |
| MC-02 | MATERIALPARTNAME input cap and wildcard | `material_parts` cap: 20 values per request; > 20 → 400 `VALIDATION_ERROR`. `*` wildcard → `LIKE %` (escaped: `_` → `\_`, `%` → `\%` before `*` → `%` translation). SQL meta-chars (`'`, `;`, `--`, `/*`, `*/`, control chars `\x00-\x1f`) in any token → 400 `VALIDATION_ERROR`; token never reaches Oracle. Exact tokens (no `*`) → `IN (...)`. Wildcard tokens → `MATERIALPARTNAME LIKE :bind ESCAPE '\'`. | unit + fuzz |
| MC-03 | Summary spool granularity key | Summary spool cache key EXCLUDES granularity. One spool file serves all three granularity views. `GET /api/material-consumption/view?query_id=X&granularity=Y` reads spool and re-groups in DuckDB; no Oracle query. Spool expiry → 410 `CACHE_EXPIRED`; client re-submits `POST /query`. | unit + resilience |
| MC-04 | Detail async threshold | `POST /api/material-consumption/detail` sync when rows ≤ `SYNC_ROW_LIMIT` (env, default 30000); async Type B (RQ queue `material-consumption`) for larger sets. Worker absent → detail jobs pending; Admin Dashboard `rq_monitor` surfaces zero workers for queue. | unit + resilience + integration |
| MC-05 | No DuckDB prewarm | No startup pre-warm performed. Cold queries hit Oracle once, populate Redis + spool cache. Subsequent requests and all granularity switches served from spool. | — (by design) |

## Downtime Analysis Rules

| rule id | name | current behavior | tests |
|---|---|---|---|
| DA-01 | E10 status filter | Only `OLDSTATUSNAME IN ('UDT','SDT','EGT')` rows from `DWH.DW_MES_RESOURCESTATUS_SHIFT` are included in all downtime-analysis aggregations. `NST` rows are excluded at the query layer. `HOURS` column is the authoritative duration source. **Implementation locus (flag ON):** query-layer SQL unchanged; raw `base_events.parquet` carries only UDT/SDT/EGT rows. | `tests/test_downtime_analysis_service.py::TestE10StatusFilter` |
| DA-02 | Cross-shift event merge | Logical-event identity = `(HISTORYID, OLDSTATUSNAME, OLDREASONNAME, run_seed_start)` where `run_seed_start` is the earliest `OLDLASTSTATUSCHANGEDATE` in the contiguous run. A run starts a new group when the gap between the prior fragment's `LASTSTATUSCHANGEDATE` and the current fragment's `OLDLASTSTATUSCHANGEDATE` exceeds 60 seconds. `hours = SUM(HOURS)`, `event_start = MIN(OLDLASTSTATUSCHANGEDATE)`, `event_end = MAX(LASTSTATUSCHANGEDATE)`. Full formal definition: `specs/changes/downtime-analysis-page/design.md §Decision 1`. **Implementation locus (flag ON):** relocated from `_merge_cross_shift_events` (server pandas) to browser DuckDB-WASM SQL in `useDowntimeDuckDB.ts`; server does NOT run this reduction on the request path. Server pandas function retained as parity reference and flag-off fallback. | `tests/test_downtime_analysis_service.py::TestCrossShiftMerge`; browser: `test_cross_shift_merge_parity_vs_reference_fixture` |
| DA-03 | JOBID bridge algorithm | Path A: `SHIFT.JOBID IS NOT NULL` → direct `JOB.JOBID = SHIFT.JOBID`; `match_source = 'jobid'`. Path B: `SHIFT.JOBID IS NULL` → candidates where `JOB.RESOURCEID = SHIFT.HISTORYID AND event_start < JOB.COMPLETEDATE AND event_end > JOB.CREATEDATE`; tiebreak by largest temporal overlap, then `JOB.CREATEDATE ASC`, then `JOB.JOBID ASC`; `match_source = 'overlap'`; `match_ambiguous = true` when runner-up overlap ≥ 80% of winner. No match: all JOB fields null, `match_source = 'none'`. Full algorithm: `specs/changes/downtime-analysis-page/design.md §Decision 2`. **Implementation locus (flag ON):** relocated from `_bridge_jobid` (server pandas) to browser DuckDB-WASM SQL in `useDowntimeDuckDB.ts`; server does NOT run this reduction on the request path. Server pandas function retained as parity reference and flag-off fallback. | `tests/test_downtime_analysis_service.py::TestJobidBridge`; browser: `test_job_overlap_bridge_parity_vs_reference_fixture` |
| DA-04 | Big-category taxonomy | Authoritative OLDREASONNAME → category mapping: `specs/changes/downtime-analysis-page/design.md §Big-category taxonomy`. Nine buckets: 維修, 保養, 改機換料, 治工具更換與模具清潔, 教讀程式, 檢查, 待料待指示, 工程 (all EGT events), 其他/未分類. OLDREASONNAME must be `strip()`ped before lookup (Oracle CHAR trailing-space). Unknown or blank → `其他/未分類`. **Implementation locus (flag ON):** server serializes `_map_big_category` to `taxonomy` JSON in the `/query` response; browser applies it as SQL CASE/join in `useDowntimeDuckDB.ts` — never hard-coded in TypeScript. Taxonomy changes require only a server redeploy; no frontend rebuild. | `tests/test_downtime_analysis_service.py::TestBigCategoryMapping`; `TestTaxonomyBuilder`; browser: `test_taxonomy_driven_big_category_identical_to_prior_server_map` |
| DA-05 | Wait/repair hours derivation | `wait_hours = (FIRSTCLOCKONDATE − CREATEDATE)` in hours; `repair_hours = (LASTCLOCKOFFDATE − FIRSTCLOCKONDATE)` in hours. Both null when `match_source = 'none'`. Null `FIRSTCLOCKONDATE` or `LASTCLOCKOFFDATE` on a matched JOB also yields null for the corresponding field. `wait_min` and `repair_min` = hours × 60, rounded to 2 d.p. **Implementation locus (flag ON):** computed in browser DuckDB-WASM after job-bridge join. | `tests/test_downtime_analysis_service.py::TestWaitRepairHours` |
| DA-06 | IT JOBID backfill cache invalidation | When IT restores `SHIFT.JOBID`, all existing `downtime_analysis_*` spool files serve stale Path-B matches. Invalidation: increment `DOWNTIME_BRIDGE_VERSION` integer in `src/mes_dashboard/config/constants.py` and redeploy; spool cache key includes this constant. Optionally purge `tmp/query_spool/downtime_analysis/*.parquet` immediately. Does not affect `resource_dataset_*` spool. Runbook documented in `ci-gates.md §Rollback Policy`. | `TestDowntimeBridgeVersionKey` |
| DA-07 | Spool TTL aligned to daily DuckDB refresh | The Redis spool metadata TTL for downtime_analysis queries is 20h (72000 s), controlled by `DOWNTIME_ANALYSIS_CACHE_TTL` env var (default 72000). This is distinct from the global `CACHE_TTL_DATASET` (2h / 7200 s); the global constant is NOT used for this service. The 20h window ensures that after the daily DuckDB prewarm refresh (keyed by `loaded_at == today`), the next user query reads newly refreshed data. | unit tests (downtime_analysis _CACHE_TTL resolves to 72000; CACHE_TTL_DATASET unchanged at 7200) |
| DA-08 | DuckDB prewarm via RQ job | At gunicorn startup, downtime_analysis DuckDB prewarm is enqueued as an RQ job registered in `spool_warmup_scheduler._WARMUP_JOBS` — previously this service had no RQ warmup entry. No `start_duckdb_prewarm()` daemon-thread call remains in `app.py`. Same leader-lock and Oracle-fallback semantics as RH-08. Prewarm covers 3 calendar months (controlled by `DOWNTIME_ANALYSIS_PREWARM_MONTHS`). | integration tests (downtime_analysis entry in _WARMUP_JOBS; Oracle call count = 1 on cold start) |
| DA-09 | 90-day Oracle-path limit removed | `_MAX_ORACLE_DAYS = 90` and its `_validate_dates` check are permanently removed from `downtime_analysis_routes.py`. The gunicorn OOM risk for >90-day Oracle-path queries is eliminated because the flag-ON path writes raw parquets and moves all pandas reductions to the browser. The 730-day SYS-04 hard cap in `_validate_dates` is retained. **Flag-OFF rollback caveat**: rolling back to flag=false accepts OOM risk on >90-day Oracle-path queries under the 6 GB/no-swap profile; short rollback windows only (see ci-gates.md §Rollback). | `tests/test_downtime_analysis_routes.py::TestMaxOracleDaysRemoved`; `TestQueryRoute::test_range_over_90_days_returns_200_not_400` |
| DA-10 | Browser memory ceiling | If DuckDB-WASM init, parquet fetch, or a reduction query fails (or estimated buffer exceeds the `duckdb-activation-policy.ts` ceiling), the composable raises a visible error banner offering a narrower date range. Zero-row result (valid empty) is explicitly distinguished from load/compute failure. Never a silent empty render (CLAUDE.md Type-A). | browser: `test_wasm_init_failure_shows_error_banner_not_empty_table`; `test_parquet_fetch_404_shows_error_banner` |
| DA-11 | Two-parquet atomicity | Server writes both `base_events.parquet` and `job_bridge.parquet` or neither. A `base_events` spool hit with a missing/expired `job_bridge` spool is a server-side error; never silently returns empty join. Browser raises a visible error if either parquet fetch returns 404/410. | `tests/test_downtime_analysis_service.py::TestTwoParquetAtomicity::test_base_hit_jobs_miss_raises_loudly` |
| DA-12 | BQE-07 raw-spool output | `query_downtime_dataset_raw()` (flag-ON path) writes one whole-dataset BQE chunk to two raw namespaces (`downtime_analysis_base_events`, `downtime_analysis_job_bridge`); no `USE_ROW_COUNT_CHUNKING` (ADR-0003 permanent exclusion). Server does not call `_merge_cross_shift_events`, `_bridge_jobid`, or `_enrich_events_df` on the request path; those reductions run in the browser. | `tests/test_downtime_analysis_service.py::TestRawSpoolWriter` |
| DDA-01 | DowntimeJob RESOURCEID+time-overlap DuckDB bridge (unified job path) | When `DOWNTIME_USE_UNIFIED_JOB=on`, `DowntimeJob` (BaseChunkedDuckDBJob, `requires_cross_chunk_reduction=True`, `chunk_strategy=SINGLE` per RESOURCEID group) streams `base_events` (keyed by HISTORYID) and `job_data` (keyed by RESOURCEID) as Arrow batches into a shared job-temp DuckDB holding tables `base_raw` and `job_raw`. `post_aggregate` runs: (a) cross-shift 60s-gap merge over `base_raw` grouped by `(HISTORYID, OLDSTATUSNAME, OLDREASONNAME)` (DA-02 algorithm in DuckDB SQL); (b) Path A equi-join (`SHIFT.JOBID IS NOT NULL`); (c) Path B RANGE JOIN time-overlap bridge (`JOIN ON base.HISTORYID = job.RESOURCEID AND job.eff_end > base.event_start AND job.CREATEDATE < base.event_end`, NOT ASOF JOIN — ADR-0010) with `overlap_s = epoch(LEAST(event_end,eff_end) - GREATEST(event_start,CREATEDATE))`, winner by `ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY overlap_s DESC, CREATEDATE ASC, JOBID ASC)`, `match_ambiguous=true` when runner-up overlap ≥ 80% of winner; (d) COPY TO unchanged `query_downtime_dataset` spool parquet (§3.21). Chunking by RESOURCEID group ensures ADR-0003's no-cross-row-reduction-at-chunk-seam invariant: each machine's events join only to that machine's jobs; chunk seams never split a HISTORYID. The N×M Cartesian `pd.merge(events_b, jobs_b, how='left')` never reaches Python heap — DuckDB on-disk spill handles candidate fan-out. Flag `off` (default): legacy `execute_downtime_query_job` → `_bridge_jobid` Path B `pd.merge` unchanged (AC-8 zero-regression). Spool output schema: §3.21 (20-column set identical for both paths, including `fragment_count` and `job_id`). | `tests/test_downtime_unified_job.py::TestDowntimeJobPostAggregate` |
| ASYNC-DA-01 | Async threshold gate | When `DOWNTIME_BROWSER_DUCKDB=true` AND `DOWNTIME_ASYNC_ENABLED=true` (env, default true) AND date range (calendar days) ≥ `DOWNTIME_ASYNC_DAY_THRESHOLD` (env, default 30) AND RQ worker available: route to async path → HTTP 202 `{async: true, job_id, status_url}`. Short queries (< threshold), disabled flag, unavailable worker, OR `DOWNTIME_BROWSER_DUCKDB=false`: synchronous path → HTTP 200 (no behavior change for existing callers). Async path requires `DOWNTIME_BROWSER_DUCKDB=true` because the worker fn writes raw-spool parquets (browser-DuckDB format). Worker dispatched via `enqueue_job_dynamic()` + `register_job_type()` (Phase 2). Cross-references: DA-11, DA-12, ADR-0003, ADR-0007, ASYNC-02. | unit tests (threshold boundary); route tests (202 vs 200) |

## Batch Query Engine Rules

| rule id | name | current behavior | tests |
|---|---|---|---|
| BQE-01 | Row-count chunking parity | With `USE_ROW_COUNT_CHUNKING=true`, each service's paged path produces the identical complete row set as the date-range path for the same filters — no dropped or duplicated rows at chunk boundaries. Spool parquet column schema is identical between paths (data-shape parity). | integration parity tests; contract shape-parity tests |
| BQE-02 | `decompose_by_row_count` correctness | `decompose_by_row_count(total_rows, rows_per_chunk)` returns a list of `{"start_row": int, "end_row": int}` dicts with inclusive 1-based ranges covering exactly `1..total_rows` with no gap and no overlap. Edge cases: `total_rows=0` → empty list; `total_rows < rows_per_chunk` → single range `{"start_row": 1, "end_row": total_rows}`; `total_rows` exact multiple → last range ends at `total_rows`; `total_rows=1` → `[{"start_row": 1, "end_row": 1}]`. | unit tests (test_batch_query_engine.py) |
| BQE-03 | Deterministic ORDER BY key per service | The `ROW_NUMBER()` ORDER BY key must be fully tie-breaking across the entire dataset to guarantee stable pagination with no row duplication or omission at chunk seams. Authoritative per-service ORDER BY keys: `production_history` — `TRACKINTIMESTAMP ASC, CONTAINERID`; `reject_dataset` — `TXN_DAY DESC, CONTAINERNAME ASC`; `resource_dataset` — `HISTORYID ASC, DATA_DATE ASC`; `hold_dataset` — `HOLDTXNDATE DESC, CONTAINERID ASC`; `job_query` — `CREATEDATE DESC, JOBID ASC`; `mid_section_defect` — `TRACKINTIMESTAMP ASC, CONTAINERID ASC`; `downtime_analysis` — `OLDLASTSTATUSCHANGEDATE DESC, HISTORYID ASC`. | data-boundary tests (tie-stability) |
| BQE-04 | Flag-off fallback guarantee | `USE_ROW_COUNT_CHUNKING=false` (default) — existing date-range chunking path is unchanged for all 7 services. No behavior change on deployment. Spool TTL, cleanup, and memory-guard behavior are unaffected by this flag in either state. | integration tests (flag=false regression) |
| BQE-05 | DB_SLOW_POOL_SIZE ceiling | `HOLD_ENGINE_PARALLEL`, `JOB_ENGINE_PARALLEL`, `MSD_ENGINE_PARALLEL` must not exceed `DB_SLOW_POOL_SIZE` (env-configurable; code default: dev=2, prod=5 per `settings.py`). A value above the ceiling silently saturates the slow pool and causes connection timeouts for other services. | env-validation tests |
| BQE-06 | Count-vs-paged consistency under non-concurrent reads | The `SELECT COUNT(*)` and paged fetches are executed without intervening DDL or concurrent data changes. Under concurrent data inserts between count and a paged fetch, the engine may see more or fewer rows than the count — this is an accepted and documented limitation. The completeness guarantee (BQE-01) applies only to non-concurrent scenarios. | resilience tests |
| BQE-07 | `downtime_analysis_service` raw-spool output | (Updated by `downtime-browser-duckdb`.) Flag ON: `query_downtime_dataset_raw()` uses one whole-dataset BQE chunk to write two raw namespaces (`downtime_analysis_base_events`, `downtime_analysis_job_bridge`); server does NOT run reductions. Flag OFF (legacy): `query_downtime_dataset()` continues to use `BatchQueryEngine → execute_plan → merge_chunks_to_spool` into the enriched `downtime_analysis_events` namespace. ADR-0003 permanent exclusion from `USE_ROW_COUNT_CHUNKING` applies to both paths. | `tests/test_downtime_analysis_service.py::TestRawSpoolWriter`; integration tests |
| BQE-08 | count_query row-unit parity with paged SQL | `count_query.sql` for each BQE service must count the same logical row unit that `dataset_paged.sql` produces in its combined CTE. When the paged CTE expands base entities (e.g., CONTAINERID) into entity × dimension pairs via JOIN (e.g., CONTAINERID × LOSSREASONNAME), `count_query.sql` must count the expanded pair set — NOT `DISTINCT` base entities. Counting only base entities while the paged SQL yields N × k pairs causes `end_row = N` to silently truncate late-range rows sorted by primary key ASC, with no error signal. Pre-fix MSD `count_query.sql` counted `DISTINCT CONTAINERID`; paged SQL yielded `detection_deduped LEFT JOIN detection_rejects` pairs — any container appearing only in the latter portion of the date range was dropped. | `tests/test_mid_section_defect_service.py` (count-parity fixture); commit e76cde22 |


## BaseChunkedDuckDBJob Fan-out Rules

| rule id | name | current behavior | tests |
|---|---|---|---|
| BJ-01 | `requires_cross_chunk_reduction` governs write topology only | `requires_cross_chunk_reduction=False` selects the multi-parquet fan-out (no shared writer-lock DuckDB). It does NOT mean no cross-row reduction exists. Any domain whose reduction spans rows from different time/ID chunks MUST perform that reduction in `post_aggregate` (reads all chunk parquets together via DuckDB glob) and MUST NOT perform it per-chunk. Setting the flag to `True` unnecessarily forces single-chunk execution and defeats parallelism. See ADR-0009 for the eap-alarm SET/CLEAR pairing precedent. | `tests/test_eap_alarm_unified_job.py` (AC-2 cross-seam fixture); `tests/test_base_chunked_duckdb_job.py` |

## EAP ALARM Rules

| rule id | name | current behavior | tests |
|---|---|---|---|
| EA-01 | Spool-key composition | EAP ALARM spool key is `eap_alarm:{date_from}:{date_to}:{coarse_dims_hash}` where `coarse_dims_hash = sha256(<canonical_repr>)[:8]`. Canonical repr covers all five coarse dims sorted: eqp_types, lot_ids (whitespace-stripped), pj_types, product_lines, pj_bops. Same full coarse-filter reuses existing parquet. `_SCHEMA_VERSION = 3` participates in the key; v2 parquet is auto-invalidated on first key-miss. | unit tests |
| EA-02 | Fine-filter derivation from DuckDB only | After spool is built, all fine-filter options (alarm_text distinct list, alarm_category decoded list, equipment_id distinct list) are derived from the DuckDB spool. Any change in fine-filter selection triggers DuckDB recompute only — never a new Oracle query. | resilience tests |
| EA-03 | LAST_UPDATE_TIME mandatory index filter | Every Oracle query against `DWH.EAP_EVENT` MUST include `LAST_UPDATE_TIME BETWEEN :date_from AND :date_to` predicate (index-driven). Full-table scans are forbidden. Missing or unbounded LAST_UPDATE_TIME → 400 `VALIDATION_ERROR`. | unit + integration tests |
| EA-04 | DETAIL data from spool only | EAP_EVENT_DETAIL parameters are JOIN-loaded into the parquet spool at query time. Detail row expansion in the UI reads from the spool. No additional Oracle query is issued. | integration tests |
| EA-05 | AlarmCategory decode table | AlarmCategory integer code is decoded to a display label using the fixed table below. Unknown code → `"未知"` fallback (never crashes). Decode applied at spool-load time; parquet stores decoded label alongside raw code. | unit tests |
| EA-06 | Spool schema version | `eap_alarm_cache.py` contains integer `_SCHEMA_VERSION` that participates in the spool cache key. Bumping orphans stale parquets by key. Schema-breaking rollback requires `rm -f tmp/query_spool/eap_alarm/*.parquet`. Column add/remove/rename MUST bump `_SCHEMA_VERSION` in the same commit. | constant-pin test |
| EA-07 | eqp_types free-form validation (closed enum retired) | `eqp_types` holds full equipment-identifier strings (e.g. `GWBK-0241`), not 4-char type codes — the field name is kept for backward compatibility though the semantic no longer matches "type". When supplied, `eqp_types` is validated exactly like `lot_ids`: each entry must be a string; non-string or blank-after-whitespace-strip entries → 400 `VALIDATION_ERROR`. There is no membership/enum check — any non-empty stripped value is accepted (the prior closed 10-value enum never matched real `DWH.EAP_EVENT.EQUIPMENT_ID` data and is dropped). Empty list (when supplied) is still treated as "not supplied" (unchanged). `_build_equipment_filter([])` emits the no-op predicate `1=1` (never an empty `IN ()`), leaving the row set unrestricted by equipment when this axis is absent — see EA-08 for how that composes with the at-least-one-of-three rule. | `tests/test_eap_alarm_service.py::TestMachinesValidation` (incl. `test_full_equipment_id_string_no_error`, `test_out_of_old_enum_value_no_longer_raises`); `tests/test_eap_alarm_service.py::TestEquipmentFilterEmptyNoOp`; `tests/integration/test_eap_alarm_resilience.py::test_empty_eqp_types_with_product_dims_only_builds_valid_sql` |
| EA-08 | Coarse-filter at-least-one rule | A spool request is accepted only when at least one of {eqp_types (non-empty after string/blank validation, EA-07), lot_ids (non-empty after whitespace-strip), product_dims (any of pj_types/product_lines/pj_bops non-empty)} is provided. All three absent or empty → 400 `VALIDATION_ERROR`. Whitespace-only lot_id strings are silently stripped before this check. When `eqp_types` is the empty/absent axis, the worker applies a `1=1` no-op equipment predicate (EA-07) — this is the exact combination that previously produced ORA-00936 in production and is now covered by regression tests. | route tests |
| EA-09 | lot_ids Oracle injection | `lot_ids` values are applied as `EAP_EVENT.LOT_ID IN (:lot_0, :lot_1, ...)`. Whitespace stripped at both key-build and Oracle bind time. Duplicates de-duplicated before binding. Max 200 lot_ids per request; exceeding this → 400 VALIDATION_ERROR. | unit + integration tests |
| EA-10 | product_dims EXISTS semi-join | When any of pj_types/product_lines/pj_bops is supplied, the Oracle query applies a separate EXISTS sub-select for each supplied dim: `EXISTS (SELECT 1 FROM DWH.DW_MES_CONTAINER c WHERE c.CONTAINERNAME = e.LOT_ID AND NVL(TRIM(c.<col>),'(NA)') IN (...))`. EXISTS prevents row explosion. Multiple dims supplied = AND-semantics (independent EXISTS per dim). Index DW_C_CONTAINERNAME is relied upon. Absent/empty individual dims are omitted. | integration tests (no-row-explosion fixture) |
| EA-ALCD | SECS/GEM ALCD sign convention | Oracle `DWH.EAP_EVENT.ALCD < 0` = SET event; `ALCD >= 0` = CLEAR event. Worker filters `ALCD < 0` for SET rows and joins CLEAR via `RESOURCEID + ALARMID + timestamp window`. Full-table scans without EA-03's `LAST_UPDATE_TIME` index predicate are forbidden. | unit + integration tests |
| EA-ASYNC | EAP ALARM unified job routing | `eap_alarm` is an always-async domain (`JobTypeConfig.always_async=True`). When `EAP_ALARM_USE_UNIFIED_JOB=on`, route enqueues via `enqueue_query_job("eap-alarm", ..., sync_fallback_allowed=False)`. Queue unavailable → HTTP 503 (ASYNC-06; never silent sync fallback). Queue available → HTTP 202. When flag is `off` (default), the legacy `run_eap_alarm_query_job` path is used unchanged (AC-8 zero-regression). ADR-0009: SET/CLEAR pairing deferred to `post_aggregate` (cross-seam safe). | `tests/test_async_query_job_service.py`, `tests/integration/test_eap_alarm_rq_async.py` |

### AlarmCategory Decode Table (EA-05)

| code | display label |
|---:|---|
| 0 | 非分類 |
| 1 | 設備 |
| 2 | 製程 |
| 3 | 視覺 |
| 4 | 機械 |
| 5 | 電子 |
| 6 | 通知/供料 |
| 7 | 品質 |
| 64 | 繼續錯誤 |
| _any other_ | 未知 |

## DB Scheduling Rules

### DB Process SPEC List (DB-00)

The 焊接_DB workcenter group contains the following 12 DB process SPECs (authoritative; any addition or removal is a business-rules breaking change requiring a new rule revision):

`1DB`, `1DB1WB`, `1DB2WB`, `2DB`, `2DB1WB`, `2DB2WB`, `DBCB`, `Epoxy D/B`, `Eutectic D/B`, `Eutectic D/B-雙晶`, `Solder Paste D/B+E-Clip`, `錫膏網印`

| rule id | name | current behavior | tests |
|---|---|---|---|
| DB-01 | D/B-START lot identification | Source lots identified by `SPECNAME = 'D/B-START'` in `DWH.DW_MES_LOT_V` (焊_DB_料 workcenter). Only these lots appear in recommendation output. | unit tests |
| DB-02 | Primary WORKFLOWNAME match | For each D/B-START lot, query `DWH.DW_MES_LOT_V` for lots at any DB-00 SPEC WHERE `STATUS = 'ACTIVE'` AND `EQUIPMENTS IS NOT NULL` AND `WORKFLOWNAME = <lot's WORKFLOWNAME>`. All distinct non-null `EQUIPMENTS` values collected as recommended equipment. One output row per equipment ID. `matchSource = "workflow"`. | unit tests |
| DB-03 | BOP fallback when no WORKFLOWNAME match | When DB-02 yields no equipment: inspect `BOP[0]` (first char of lot's BOP field). Dispatch: `U` → query ACTIVE equipment at `{1DB, 1DB1WB, 1DB2WB, 2DB, 2DB1WB, 2DB2WB, Eutectic D/B, Eutectic D/B-雙晶}`; `E` → query ACTIVE equipment at `{Epoxy D/B}`; `P` → query ACTIVE equipment at `{DBCB, Solder Paste D/B+E-Clip, 錫膏網印}`; other/null → `matchSource = "none"`, no row emitted, no error. `matchSource = "bop-fallback"` for U/E/P matches. | unit tests |
| DB-04 | Sort order | Output rows sorted: `PACKAGE_LEF ASC` → `PJ_TYPE ASC` → `WAFERLOT ASC` → `UTS ASC`. Null values in any sort key sorted last (NULLS LAST). | unit tests |
| DB-05 | Read-only; no MES writes | Endpoint is strictly GET-only. Queries `DWH.DW_MES_LOT_V` (existing 5-min WIP cache). Does NOT write to Oracle, MES, Redis, or any store. Equipment assignment is advisory only. | — (by design, AC-7) |

## Change Policy

任何業務邏輯變更必須：
1. 更新此文件的相關 rule。
2. 更新受影響的 decision table 行。
3. 新增或更新對應的回歸測試。
4. 若行為是 breaking change（影響 client），走 deprecate-2-minors 流程。

## CHANGELOG

## [business 1.42.0] — 2026-07-02
### Added
- production-achievement-kanban: Added `## Production-Achievement Rules` section (PA-01..PA-07) — two-shift/three-shift SHIFT_CODE classification (re-implements `PJ_GET_CLASSCODE_F`), output_date cross-night attribution (re-implements `PJ_GET_OUTPUTDATE_F`; three-shift C-band explicitly flagged as an UNVERIFIED ASSUMPTION per user's Open Questions), effective-output station/process qualifying predicate (SPECNAME + processtypename/WORKFLOWNAME 雙晶/三晶 combinations, preserved verbatim), achievement-rate grouping/formula reusing `filter_cache.get_spec_workcenter_mapping()`, and division-by-zero/missing-target null semantics. Fifteen new Decision Table rows. Additive; no existing rules changed.

## [business 1.41.0] — 2026-07-01
### Changed
- eap-alarm-coarse-filter (post-ship correction): EA-07 rewritten — the closed 10-value `eqp_types` enum is dropped (it never matched real `DWH.EAP_EVENT.EQUIPMENT_ID` data, which is `<prefix>-<instance>`, not a bare 4-char code); replacement rule validates `eqp_types` exactly like `lot_ids` (non-string/blank entries rejected, any non-empty stripped string accepted, no membership check). Field name `eqp_types` is kept unchanged for backward compatibility despite now holding full equipment-identifier strings. EA-07 also documents the `_build_equipment_filter([])` → `1=1` no-op fix (was an unconditional empty `IN ()` causing ORA-00936 in production for the EA-08-legal `eqp_types=[]` + non-empty product-dim combo). EA-08 wording touched up to remove its stale "after enum validation" phrase; at-least-one-of-three semantics unchanged. No API/schema/spool-key-dimension change — bugfix + data-model correction only.

## [business 1.40.0] — 2026-07-01
### Added
- yield-alert-kpi-csv-parity: YA-13 — KPI summary (`GET /api/yield-alert/view` / `GET /api/yield-alert/summary` `summary.transaction_qty`/`summary.scrap_qty`) scope unified to match the alert-candidate predicate (`SCRAP_QTY<>0`, risk_threshold/min_scrap_qty exclusion, full 6-dim filters) instead of the prior broader scope; documents the `tx_extra_cols` dedup dimension (excludes REASON_CODE/REASON_NAME) required to avoid double-counting `transaction_qty` when a group has multiple distinct reason_codes. Scope limited to the top-level KPI summary; trend/heatmap/station/package summaries unaffected (non-goal).

## [business 1.38.0] — 2026-07-01
### Changed
- yield-alert-filter-expansion: YA-01 process_type enum expands `{GA%,GC%}` → `{GA%,GC%,GD%,F%,W%,D%}`. YA-02 rewritten as the full prefix → WIP_CLASS_CODE mapping table (verified via direct Oracle query) with mutual-exclusivity guarantee. New YA-02a documents the GA% non-split non-goal. New YA-10/YA-11/YA-12 document the `workcenter_groups` source swap (global filter_cache → per-query_id spool `SELECT DISTINCT DEPARTMENT_NAME`) for `GET /api/yield-alert/view` and `GET /api/yield-alert/cross-filter-options` only; `GET /api/yield-alert/filter-options` and other filter_cache consumers unaffected.

## [business 1.32.0] — 2026-06-26
### Added
- add-db-scheduling-page: `## DB Scheduling Rules` section (DB-01..DB-05) + DB-00 authoritative 12-SPEC list: D/B-START lot identification (SPECNAME='D/B-START'), primary WORKFLOWNAME match (STATUS=ACTIVE + EQUIPMENTS NOT NULL), BOP fallback U/E/P dispatch groups, NULLS LAST sort order, read-only constraint. Five new Decision Table rows. Additive; no existing rules changed.

## [business 1.31.0] — 2026-06-25
### Added
- rh-remove-supplementary-filter: RHPF-07 (NVL/TRIM NULL-LOSSREASONNAME sentinel — `reasons[]` uses `(未填寫)` sentinel distinct from container-level `(NA)`; source is LOTREJECTHISTORY direct column, not LEFT JOIN; selecting `(未填寫)` returns null/blank LOSSREASONNAME rows; options from `reason_filter_cache`). RHPF-08 (WHERE-semantics equivalence — BASE_WHERE `reasons[]` produces identical result sets to prior supplementary DuckDB-layer reason filter for same selection including `(未填寫)` bucket). Extended RHPF-01 (now covers all four prefilter fields; supplementary `{{ WHERE_CLAUSE }}` layer removal noted). Extended RHPF-02 (now covers four fields). Updated RHPF-05 (parity rule now covers all four fields). Four new Decision Table rows (`reasons[]` non-empty, `reasons[]` empty, `(未填寫)` bucket, `workcenter_groups` ignored). Additive; no existing rules removed.

## [business 1.30.0] — 2026-06-25
### Added
- rh-primary-prefilter: Added `## Reject-History Prefilter Rules` section (RHPF-01..RHPF-06):
  BASE_WHERE injection point distinction from WHERE_CLAUSE (RHPF-01); empty-selection = no restriction /
  backward-compatible (RHPF-02); NVL/TRIM NULL-container sentinel `(NA)` — NULL rows not silently dropped,
  selecting `(NA)` returns NULL-container rows (RHPF-03); PJ_BOP explicitly excluded (RHPF-04);
  sync/async path parity + spool/cache key inclusion (RHPF-05); options from shared `container_filter_cache`
  read-only (RHPF-06). Four new Decision Table rows. Additive; no existing rules changed.

## [business 1.29.0] — 2026-06-20
### Added
- rq-semaphore-wiring: ASYNC-15 (Oracle-phase RQ concurrency cap — `HEAVY_QUERY_MAX_CONCURRENT` (default 3) bounds simultaneous Oracle-phase executions across all four `execute_*_job` workers; slot acquired once per job around Oracle fetch, released on success and exception; `execute_reject_query_job` wired at cache layer only; Redis-down fail-open). Two Decision Table rows (N>cap burst + exception-during-slot). Additive; no existing rules changed.

## [business 1.27.0] — 2026-06-19
### Added
- downtime-duckdb-join-migration: DDA-01 (DowntimeJob RESOURCEID+time-overlap DuckDB bridge — `DOWNTIME_USE_UNIFIED_JOB=on` streams base_events + job_data Arrow batches into two-table job-temp DuckDB, runs cross-shift 60s-gap merge + RANGE JOIN time-overlap bridge in post_aggregate (ADR-0010; NOT ASOF JOIN); `COPY TO` unchanged query_downtime_dataset spool (§3.21). `requires_cross_chunk_reduction=True`, `chunk_strategy=SINGLE` per RESOURCEID group, ADR-0003 preserved. N×M Cartesian pd.merge eliminated; DuckDB on-disk spill absorbs candidate fan-out. Flag `off`: legacy _bridge_jobid Path B unchanged (AC-8). Three new Decision Table rows. Additive; no existing rules changed.

## [business 1.26.1] — 2026-06-19
### Added
- eap-alarm-unified-job-poc: BJ-01 (`requires_cross_chunk_reduction` governs write topology only; post_aggregate is the safe deferral point for cross-row reductions that span chunk boundaries — see ADR-0009). New `## BaseChunkedDuckDBJob Fan-out Rules` section. Additive; no existing rules changed.

## [business 1.26.0] — 2026-06-19
### Added
- material-trace-streaming-migration: ASYNC-10 (unified-job dispatch for material-trace domain — `MATERIAL_TRACE_USE_UNIFIED_JOB=on` routes to `MaterialTraceJob` via `enqueue_query_job("material-trace-unified", always_async=True, sync_fallback_allowed=False)`; async unavailable → 503, no sync fallback; ID-list 1000/batch chunking; post_aggregate DISTINCT on exact 4-col key; WORKCENTER_GROUP enrichment inline; spool namespace+schema unchanged). ASYNC-11 (heavy-query semaphore role re-statement: `global_concurrency.acquire_heavy_query_slot` semantics shift to cap concurrent RQ Oracle jobs; no code change). Three new Decision Table rows (material-trace flag-on/async-available, flag-on/async-unavailable, flag-off paths). Additive; no existing rules changed.

## [business 1.25.0] — 2026-06-19
### Added
- resource-history-migration: ASYNC-09 (dual-job unified execution rule for resource-history domain — `RESOURCE_HISTORY_USE_UNIFIED_JOB=on` routes to two RQ jobs: `resource-history-base` (`always_async=True`, `requires_cross_chunk_reduction=False`) and `resource-history-oee` (`always_async=True`, `requires_cross_chunk_reduction=True`); queue unavailable → 503 with Retry-After; OEE ratio-of-SUMs via job-temp DuckDB `post_aggregate`; ±30d reject window per chunk; spool schemas per §3.19; flag-off uses legacy `export_csv` unchanged). Additive; no existing rules changed.

## [business 1.24.0] — 2026-06-19
### Added
- production-reject-history-migration: ASYNC-07 (unified-job dispatch rule — `<DOMAIN>_USE_UNIFIED_JOB=on` routes to `enqueue_query_job` with `always_async=False` and `sync_fallback_allowed=True`; flag-off uses legacy path verbatim; independent per-domain flags). ASYNC-08 (OOM guard shift — unified job path uses DuckDB COPY/on-disk spill; legacy flag=off path retains existing guards unchanged; ast-absence test confirms no `len(df)/memory_usage`-IF-raise patterns in new worker modules or legacy files). Six new Decision Table rows for production_history and reject unified/legacy/unavailable paths. EA-ASYNC rule supplemented with P2 context (production_history + reject). Additive; no existing rules changed.

## [business 1.37.0] — 2026-06-30
### Added
- eap-alarm-coarse-filter: EA-08 (at-least-one-of-three coarse-filter validation), EA-09 (lot_ids Oracle IN injection — strip/dedup/max-200), EA-10 (product_dims EXISTS semi-join — no row explosion, AND-semantics, DW_C_CONTAINERNAME index). EA-01 updated (spool-key hash extended to all 5 dims). EA-07 updated (eqp_types validation applies only when supplied; empty no longer unconditional 400). Additive; no existing rules removed.

## [business 1.23.0] — 2026-06-18
### Added
- eap-alarm-unified-job-poc: ASYNC-06 (always-async 503 forced rule for `EapAlarmJob`: when `always_async=True` and `sync_fallback_allowed=False` and queue unavailable → HTTP 503, no silent sync downgrade). EA-ASYNC rule (EAP alarm unified-job routing decision table: flag-on/async-available, flag-on/async-unavailable, flag-off paths). Additive; no existing rules changed.

## [business 1.22.0] — 2026-06-18
### Added
- eap-alarm-analysis: Added EAP ALARM Rules section (EA-01..EA-07) — spool-key composition, DuckDB-only fine-filter derivation, LAST_UPDATE_TIME mandatory index filter, DETAIL from spool only, AlarmCategory fixed decode table (9 codes + unknown fallback), spool schema version governance, EQP type closed enum (10 values). AlarmCategory Decode Table block added. Additive; no existing rules changed.

## [business 1.21.0] — 2026-06-16
### Added
- yield-alert-spool-refactor: Added YA-01..YA-09 (Yield Alert Rules section) covering process-type scope (GA%/GC% enum, default GA%, VALIDATION_ERROR on invalid), GA%/GC% domain distinction, PACKAGE IS NOT NULL filter removal rationale (0 GA% rows affected), SOURCE_CODE NOT NULL ⇒ TX_QTY=0 invariant, LOT dimension in alert list (display only; yield formula unchanged), spool-first view serving (Type A spool pattern; live Oracle trend/summary paths retired), reject linkage in single spool pull (_compute_reject_linkage retired), ERP_WIP_MOVETXN_DETAIL as data source (totals verified identical), and spool schema version governance. Additive; no existing rules changed.

## [business 1.11.0]
- ai-pipeline-upgrade (2026-05-29): Added AI-04 (combined-prompt output schema), AI-05 (malformed-JSON fallback), AI-06 (chat_history append policy), AI-07 (chat_history cap/eviction), AI-08 (history injection ordering), AI-09 (three new function behaviors). Updated AI-01 description to reflect combined-call. Additive; no existing rules changed.

## [business 1.10.0]
- material-part-consumption (2026-05-20): Added MC-01..MC-05 rules for the new material-consumption report (aggregation grouping, input cap/wildcard/meta-char, granularity cache key exclusion, async threshold, no prewarm). Additive; no existing rules changed.
