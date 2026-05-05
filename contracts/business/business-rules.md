---
contract: business
summary: Business decision tables, rule inventory, and change policy for behavior updates.
owner: application-team
surface: domain-behavior
schema-version: 1.0.0
last-changed: 2026-05-05
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

## Change Policy

任何業務邏輯變更必須：
1. 更新此文件的相關 rule。
2. 更新受影響的 decision table 行。
3. 新增或更新對應的回歸測試。
4. 若行為是 breaking change（影響 client），走 deprecate-2-minors 流程。
