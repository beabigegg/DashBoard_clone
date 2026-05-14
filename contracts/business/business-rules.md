---
contract: business
summary: Business decision tables, rule inventory, and change policy for behavior updates.
owner: application-team
surface: domain-behavior
schema-version: 1.4.0
last-changed: 2026-05-14
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
| AI-01 | Pipeline selection | `AI_MODE` env 決定：`text2sql`（分類→SQL→執行→摘要）、`function`（3-round function call）、`agent`（多工具 agentic loop） |
| AI-02 | Clarification flag | `needs_clarification: true` 表示 AI 需要更多資訊，而非最終答案；`text2sql` / `function` mode 永遠為 `false` |
| AI-03 | Response fields | `{answer, chart_data, query_used, params_used, suggestions, sql_used, tool_trace, needs_clarification}` |

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

## Resource History Rules

| rule id | name | current behavior | tests |
|---|---|---|---|
| RH-01 | Type A spool pattern | `POST /api/resource/history/query` → spool 存 DuckDB；view miss → 410 → client 重觸發（Type A）；response shape: `{query_id, summary, detail}` | resilience tests |
| RH-02 | Local compute flag | `RESOURCE_HISTORY_LOCAL_COMPUTE_ENABLED` env（預設 `true`）；`false` 時 `/page` endpoint 回重導向至舊路徑 | unit tests |
| RH-03 | Metadata injection | `_inject_resource_spool_info` 與 `_inject_resource_metadata` 自動將 spool info 與設備 metadata 注入 response | unit tests |
| RH-04 | Date validation | `start_date` / `end_date` 必需；無效日期格式或超過 730d → 400 `VALIDATION_ERROR` | route tests |

## Production-History Rules

| rule id | name | current behavior | tests |
|---|---|---|---|
| PH-01 | Raw per-partial detail rows | Detail query returns one row per LOTWIPHISTORY partial track-out (no GROUP BY). `TRACKINTIMESTAMP / TRACKOUTTIMESTAMP / TRACKINQTY / TRACKOUTQTY` are raw per-partial values — prior assumption "first partial = original batch quantity" is dropped | unit + parity tests |
| PH-02 | Matrix lot-count semantics | Matrix `count` cell = `COUNT(DISTINCT CONTAINERNAME)` computed in DuckDB over the raw row source; equals prior aggregated-baseline lot count for the same (WC, Spec, Equipment × Month) cell | integration + e2e tests |
| PH-03 | PJ_FUNCTION spool carriage | `PJ_FUNCTION` is carried through Oracle→spool→DuckDB schema and CSV export (pre-staged for Change 3); not yet exposed as a user filter | contract + parity tests |
| PH-04 | Detail row ordering | Detail table sorts by `TRACKINTIMESTAMP` ascending; no "partial #" column (Resolved Decision 2 of change `prod-history-detail-raw-rows`) | e2e tests |

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

## Admin Rules

| rule id | name | current behavior | tests |
|---|---|---|---|
| ADMIN-01 | Double auth gate | Admin 端點需同時通過 `login_required` + `is_admin` check；缺少任一 → 403 `FORBIDDEN` | route tests |
| ADMIN-02 | Performance metrics | `/admin/api/performance-history` 儲存 API response time 歷史；`/purge` 清空；`/detail` 查詢單次請求詳情 | route tests |
| ADMIN-03 | Worker management | `POST /admin/api/worker/restart` 重啟 RQ worker；`GET /worker/status` 查 worker 狀態；需 admin | route tests |
| ADMIN-04 | Drawer CRUD | `/admin/api/drawers` 管理導覽欄 drawer 設定；支援 CRUD（GET/POST/PUT/DELETE）| route tests |
| ADMIN-05 | Log management | `/admin/api/logs`、`/logs/cleanup`、`/log-files/cleanup` 管理系統 log；cleanup 用 DELETE method | route tests |

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

## Change Policy

任何業務邏輯變更必須：
1. 更新此文件的相關 rule。
2. 更新受影響的 decision table 行。
3. 新增或更新對應的回歸測試。
4. 若行為是 breaking change（影響 client），走 deprecate-2-minors 流程。
