---
contract: env
summary: Environment variable inventory, secret handling, and deployment sync policy.
owner: platform-team
surface: runtime-config
schema-version: 1.0.18
last-changed: 2026-06-19
breaking-change-policy: deprecate-2-minors
---

# Env Contract — MES Dashboard

> 來源：掃描 `.env`（2026-05-05）  
> 密碼/連線字串以 `.env` 為唯一事實來源；此契約只記錄名稱、用途與驗證規則。  
> 欄位順序：name | scope | environments | required | secret | default | example | owner | validation | restart required | failure behavior

---

## Flask / App Core

| name | scope | environments | required | secret | default | example | owner | validation | restart required | failure behavior |
|---|---|---|---:|---:|---|---|---|---|---:|---|
| FLASK_ENV | app | all | yes | no | production | production | platform-team | must be production or development | yes | 影響 security 設定 |
| FLASK_DEBUG | app | all | yes | no | 0 | 0 | platform-team | 0 or 1; production must be 0 | yes | debug mode 錯誤暴露 |
| SECRET_KEY | app | all | yes | yes | — | — | platform-team | ≥32 bytes high-entropy string | yes | 啟動失敗 |
| SESSION_LIFETIME | app | all | no | no | 28800 | 28800 | platform-team | positive integer (seconds) | no | 使用預設 |
| PERMANENT_SESSION_LIFETIME | app | all | no | no | 28800 | 28800 | platform-team | positive integer (seconds) | no | 使用預設 |
| LOGIN_SESSION_SQLITE_PATH | app | all | no | no | logs/login_sessions.sqlite | logs/login_sessions.sqlite | platform-team | writable path | no | fallback to in-memory |

## Database（Oracle）

| name | scope | environments | required | secret | default | example | owner | validation | restart required | failure behavior |
|---|---|---|---:|---:|---|---|---|---|---:|---|
| DB_HOST | db | all | yes | no | — | 10.1.1.58 | platform-team | reachable hostname or IP | yes | DB 連線失敗 → 503 |
| DB_PORT | db | all | yes | no | 1521 | 1521 | platform-team | valid port 1-65535 | yes | DB 連線失敗 |
| DB_SERVICE | db | all | yes | no | — | DWDB | platform-team | non-empty string | yes | DB 連線失敗 |
| DB_USER | db | all | yes | yes | — | — | platform-team | non-empty string | yes | DB 連線失敗 |
| DB_PASSWORD | db | all | yes | yes | — | — | platform-team | non-empty string | yes | DB 連線失敗 |

## Auth（LDAP / Local）

| name | scope | environments | required | secret | default | example | owner | validation | restart required | failure behavior |
|---|---|---|---:|---:|---|---|---|---|---:|---|
| LDAP_API_URL | auth | all | yes | no | — | https://adapi.example.com | platform-team | valid HTTPS URL | yes | 登入失敗 |
| ADMIN_EMAILS | auth | all | no | no | — | admin@example.com | platform-team | comma-separated emails | no | 無 admin 用戶 |
| LOCAL_AUTH_ENABLED | auth | dev | no | no | false | false | platform-team | true or false | yes | dev only |
| LOCAL_AUTH_USERNAME | auth | dev | no | yes | — | — | platform-team | non-empty if LOCAL_AUTH_ENABLED=true | yes | 本地登入失敗 |
| LOCAL_AUTH_PASSWORD | auth | dev | no | yes | — | — | platform-team | non-empty if LOCAL_AUTH_ENABLED=true | yes | 本地登入失敗 |

## Redis

| name | scope | environments | required | secret | default | example | owner | validation | restart required | failure behavior |
|---|---|---|---:|---:|---|---|---|---|---:|---|
| REDIS_URL | redis | all | yes | no | redis://localhost:6379/0 | redis://localhost:6379/0 | platform-team | valid redis:// URL | yes | cache 降級、RQ 失敗 |
| REDIS_ENABLED | redis | all | no | no | true | true | platform-team | true or false | yes | false = 停用快取 |
| REDIS_KEY_PREFIX | redis | all | no | no | mes_wip | mes_wip | platform-team | non-empty string | no | — |
| REDIS_PERSISTENCE_ENABLED | redis | all | no | no | true | true | platform-team | true or false | no | — |
| REDIS_MAXMEMORY_POLICY | redis | all | no | no | allkeys-lru | allkeys-lru | platform-team | valid Redis policy | no | — |
| CACHE_CHECK_INTERVAL | redis | all | no | no | 600 | 600 | platform-team | positive integer (seconds) | no | — |

## Frontend Build

| name | scope | environments | required | secret | default | example | owner | validation | restart required | failure behavior |
|---|---|---|---:|---:|---|---|---|---|---:|---|
| PORTAL_SPA_ENABLED | frontend | all | yes | no | true | true | application-team | true or false | yes | 停用 SPA 模式 |
| MODERNIZATION_ENFORCE_ASSET_READINESS | frontend | all | no | no | true | true | application-team | true or false | yes | 資產未就緒時啟動失敗 |
| FRONTEND_BUILD_MODE | frontend | all | no | no | always | always | application-team | always or on-demand | yes | — |
| FRONTEND_BUILD_FAIL_ON_ERROR | frontend | all | no | no | true | true | application-team | true or false | yes | build 錯誤不中止 |
| RUNTIME_CONTRACT_ENFORCE | frontend | all | no | no | true | true | application-team | true or false | yes | 停用 contract 驗證 |

## Feature Flags

| name | scope | environments | required | secret | default | example | owner | validation | restart required | failure behavior |
|---|---|---|---:|---:|---|---|---|---|---:|---|
| AI_QUERY_ENABLED | feature | all | no | no | — | true | application-team | true or false | yes | AI 端點返回 404 |
| AI_MODE | feature | all | no | no | text2sql | text2sql | application-team | text2sql, function, or agent | yes | fallback to text2sql |
| ANALYTICS_ANOMALY_DETECTION_ENABLED | feature | all | no | no | — | true | application-team | true or false | yes | anomaly 端點 404 |
| PROD_HISTORY_ENABLED | feature | all | no | no | — | true | application-team | true or false | yes | production-history 端點 404 |
| REGISTER_INTERNAL_METRICS | feature | dev | no | no | False | False | platform-team | True or False — production MUST NOT set True | yes | internal metrics blueprint 掛載 |
| INTERNAL_METRICS_ENABLED | feature | dev | no | no | 0 | 0 | platform-team | 0 or 1 — production MUST NOT set 1 | no | handler guard |
| EAP_ALARM_USE_UNIFIED_JOB | feature | all | no | no | off | off | application-team | off/on or false/true or 0/1; selects unified EapAlarmJob path (on) vs legacy run_eap_alarm_query_job (off). Restart required. | yes | uses default off |
| PRODUCTION_HISTORY_USE_UNIFIED_JOB | feature | all | no | no | off | off | application-team | off/on or false/true or 0/1; selects unified ProductionHistoryJob path (on) vs legacy pandas BQE path (off). Restart required. | yes | uses default off |
| REJECT_HISTORY_USE_UNIFIED_JOB | feature | all | no | no | off | off | application-team | off/on or false/true or 0/1; selects unified RejectHistoryJob path (on) vs legacy execute_primary_query path (off). Restart required. | yes | uses default off |
| RESOURCE_HISTORY_USE_UNIFIED_JOB | feature | all | no | no | off | off | application-team | off/on or false/true or 0/1; selects unified ResourceHistoryBaseJob+ResourceHistoryOeeJob path (on) vs legacy export_csv Oracle read path (off). Restart required. | yes | uses default off |
| MATERIAL_TRACE_USE_UNIFIED_JOB | feature | all | no | no | off | off | application-team | off/on or false/true or 0/1; selects unified MaterialTraceJob path (on) vs legacy _execute_batched_query_to_parquet path (off). always_async=True; async unavailable → 503 (no sync fallback). Restart required. | yes | uses default off |

- `EAP_ALARM_USE_UNIFIED_JOB`: Feature flag enabling the unified `EapAlarmJob` path (`BaseChunkedDuckDBJob` template method). When `on`/`true`/`1`, the eap_alarm route enqueues via `enqueue_query_job` + `EapAlarmJob`; the always-async 503 decision tree applies (`sync_fallback_allowed=False`). When `off` (default)/`false`/`0`, the legacy `run_eap_alarm_query_job` path is used unchanged (AC-8 zero-regression guarantee). Module-level constant frozen at import — restart required. `monkeypatch.setattr()` required in tests (not `setenv`). Must be `off` in production until AC-1 parity tests pass. Added by change `eap-alarm-unified-job-poc`.
- `PRODUCTION_HISTORY_USE_UNIFIED_JOB`: Feature flag enabling the unified `ProductionHistoryJob` path (`BaseChunkedDuckDBJob` template method, P2 migration). When `on`/`true`/`1`, production_history route enqueues via `enqueue_query_job("production_history_unified", ..., sync_fallback_allowed=True)`; `always_async=False` so sync fallback is permitted. When `off` (default)/`false`/`0`, the legacy `query_production_history` pandas BQE path is used unchanged (AC-8 zero-regression). Module-level constant `_PRODUCTION_HISTORY_USE_UNIFIED_JOB` frozen at import — restart required. `monkeypatch.setattr()` required in tests. Added by change `production-reject-history-migration`.
- `REJECT_HISTORY_USE_UNIFIED_JOB`: Feature flag enabling the unified `RejectHistoryJob` path (`BaseChunkedDuckDBJob` template method, P2 migration). When `on`/`true`/`1`, reject_history route enqueues via `enqueue_query_job("reject_unified", ..., sync_fallback_allowed=True)`; `always_async=False` so sync fallback is permitted; `requires_cross_chunk_reduction=True` so DuckDB `post_aggregate` runs GROUP BY/pareto/trend. When `off` (default)/`false`/`0`, the legacy `enqueue_reject_query` path is used unchanged (AC-8 zero-regression). Module-level constant `_REJECT_HISTORY_USE_UNIFIED_JOB` frozen at import — restart required. `monkeypatch.setattr()` required in tests. Added by change `production-reject-history-migration`.
- `RESOURCE_HISTORY_USE_UNIFIED_JOB`: Feature flag enabling the unified `ResourceHistoryBaseJob` + `ResourceHistoryOeeJob` path (`BaseChunkedDuckDBJob` template method, P3 migration). When `on`/`true`/`1`, the resource-history export route enqueues TWO RQ jobs (base facts + OEE facts) via `enqueue_query_job` with `always_async=True` and `sync_fallback_allowed=False`; sync fallback is removed — degraded (worker unavailable) returns 503. The CSV stitch reads from the two parquet spools via DuckDB join (`export_csv_from_spools`). When `off` (default)/`false`/`0`, the legacy `export_csv` Oracle read + iterrows path is used unchanged (AC-1 zero-regression). Module-level constants `RESOURCE_HISTORY_USE_UNIFIED_JOB` (routes) and `_RESOURCE_HISTORY_USE_UNIFIED_JOB` (service) frozen at import — restart required. `monkeypatch.setattr()` required in tests. **Worker env-var parity**: the `mes-dashboard-resource-history-worker.service` systemd unit MUST export `RESOURCE_HISTORY_USE_UNIFIED_JOB` with the same value as gunicorn. Added by change `resource-history-migration`.
- `MATERIAL_TRACE_USE_UNIFIED_JOB`: Feature flag enabling the unified `MaterialTraceJob` path (`BaseChunkedDuckDBJob` template method, P4 migration). When `on`/`true`/`1`, the material-trace query route uses `enqueue_query_job("material-trace-unified", ..., sync_fallback_allowed=False)` with `always_async=True`; async unavailable → 503 (no silent sync fallback — D4 decision). When `off` (default)/`false`/`0`, the legacy `_execute_batched_query_to_parquet` path is used unchanged (AC-1 zero-regression). Spool namespace `material_trace` and parquet schema are unchanged — frontend `/view` and CSV export need no change. Module-level constant `MATERIAL_TRACE_USE_UNIFIED_JOB` frozen at import — restart required. `monkeypatch.setattr()` required in tests. **Worker env-var parity**: the `mes-dashboard-trace-worker.service` systemd unit MUST export `MATERIAL_TRACE_USE_UNIFIED_JOB` with the same value as gunicorn. Added by change `material-trace-streaming-migration`.

**Worker env-var parity (P2 — production-reject-history-migration):** The `mes-dashboard-production-history-worker.service` systemd unit MUST export `PRODUCTION_HISTORY_USE_UNIFIED_JOB` with the same value as gunicorn. The `mes-dashboard-reject-worker.service` systemd unit MUST export `REJECT_HISTORY_USE_UNIFIED_JOB` with the same value as gunicorn. Both flags are module-level constants frozen at worker boot; env-var drift between gunicorn and a worker process silently routes different code paths per process (gunicorn = unified job, worker = legacy, or vice versa), breaking spool-parity guarantees. Validate via deploy-time env comparison before enabling either flag. Added by change `production-reject-history-migration`.

## Cache Tuning — Resource History

| name | scope | environments | required | secret | default | example | owner | validation | restart required | failure behavior |
|---|---|---|---:|---:|---|---|---|---|---:|---|
| RESOURCE_HISTORY_HISTORICAL_TTL | cache | all | no | no | 86400 | 86400 | application-team | positive integer (seconds); minimum 3600 | yes | uses default 86400 |
| RESOURCE_HISTORY_SPOOL_TTL | cache | all | no | no | 72000 | 72000 | application-team | positive integer (seconds); minimum 3600; controls Redis spool metadata TTL for recent resource_history queries; overrides CACHE_TTL_DATASET for this service | yes | uses default 72000 |
| RESOURCE_VIEW_CACHE_TTL | cache | all | no | no | 300 | 300 | application-team | non-negative integer (seconds); 0 disables view-result cache | yes | uses default 300 |
| RESOURCE_HISTORY_PREWARM_MONTHS | cache | all | no | no | 3 | 3 | application-team | positive integer 1–12; 0 disables DuckDB prewarm | yes | uses default 3 |
| DOWNTIME_BROWSER_DUCKDB | feature-flag | all | no | no | false | true | application-team | boolean (1/true/yes = enabled); governs whether `POST /api/downtime-analysis/query` returns raw-spool URLs for browser DuckDB-WASM (`true`) or the legacy enriched-spool response (`false`); restart required to take effect (module-level constant frozen at import) | yes | uses default false |
| DOWNTIME_ANALYSIS_CACHE_TTL | cache | all | no | no | 72000 | 72000 | application-team | positive integer (seconds); minimum 3600; controls Redis spool metadata TTL for downtime_analysis queries; overrides CACHE_TTL_DATASET for this service | yes | uses default 72000 |
| DOWNTIME_ANALYSIS_PREWARM_DAYS | cache | all | no | no | 30 | 30 | application-team | deprecated — superseded by DOWNTIME_ANALYSIS_PREWARM_MONTHS; kept for backward compat | yes | uses default 30 |
| DOWNTIME_ANALYSIS_PREWARM_MONTHS | cache | all | no | no | 3 | 3 | application-team | positive integer 1–12; 0 disables DuckDB prewarm | yes | uses default 3 |
| DOWNTIME_ANALYSIS_DUCKDB_PATH | storage | all | no | no | tmp/downtime_analysis.duckdb | /var/lib/mes/downtime_analysis.duckdb | application-team | file path (relative resolved to CWD; use absolute for Docker) | yes | uses default path |
| RESOURCE_HISTORY_DUCKDB_PATH | storage | all | no | no | tmp/resource_history.duckdb | /var/lib/mes/resource_history.duckdb | application-team | file path (relative resolved to CWD; use absolute for Docker) | yes | uses default path |

- `RESOURCE_HISTORY_HISTORICAL_TTL`: Redis TTL for resource-history queries where `end_date < today − 2 days`. Historical data is immutable; default 86400s (24h). Added by change `resource-history-perf`.
- `RESOURCE_HISTORY_SPOOL_TTL`: Redis spool metadata TTL for recent resource_history queries (end_date ≥ today − 2d). Default 72000 s (20h), aligned to the daily DuckDB refresh cycle. Overrides `CACHE_TTL_DATASET` (2h) for this service specifically; hold/reject/yield_alert datasets are unaffected. Set to a value slightly less than 86400 to guarantee daily refresh takes effect. Restart required. Added by change `unify-duckdb-prewarm-rq`.
- `RESOURCE_HISTORY_PREWARM_MONTHS`: Number of calendar months of resource-history data to load into the persistent DuckDB cache at startup. Background thread starts 10s after worker boot; `0` disables entirely. Default 3 months (~25s Oracle load time, ~15MB DuckDB file). Added by change `resource-history-perf`.
- `DOWNTIME_BROWSER_DUCKDB`: Feature flag controlling the `POST /api/downtime-analysis/query` response path. `true` (or `1`/`yes`) → returns `{base_spool_url, jobs_spool_url, query_id, taxonomy}` for browser DuckDB-WASM processing; `false` (default at initial ship) → returns prior `{query_id, summary, daily_trend, big_category, top_reasons}` enriched-spool response. Default `false` chosen for safety — parity sign-off required before enabling in production. **Restart required** — module-level constant `_BROWSER_DUCKDB_ENABLED` in `downtime_analysis_routes.py` is frozen at import time; `monkeypatch.setattr()` required in tests (never `os.environ`). Added by change `downtime-browser-duckdb`.
- `DOWNTIME_ANALYSIS_PREWARM_DAYS`: Deprecated — superseded by `DOWNTIME_ANALYSIS_PREWARM_MONTHS` and the DuckDB persistent cache. Kept for backward compatibility. Default 30 days.
- `DOWNTIME_ANALYSIS_CACHE_TTL`: Redis spool metadata TTL for downtime_analysis queries. Default 72000 s (20h), aligned to the daily DuckDB refresh cycle. Overrides `CACHE_TTL_DATASET` (2h) for this service; other dataset TTLs are unaffected. Restart required. Added by change `unify-duckdb-prewarm-rq` (previously existed in code but undocumented).
- `DOWNTIME_ANALYSIS_PREWARM_MONTHS`: Number of calendar months of downtime-analysis data to load into the persistent DuckDB cache at startup. DuckDB prewarm now runs via RQ job (not daemon thread); `0` disables entirely. Default 3 months. Added by change `downtime-analysis-duckdb-cache`; startup mechanism updated by `unify-duckdb-prewarm-rq`.
- `DOWNTIME_ANALYSIS_DUCKDB_PATH`: Path to the persistent DuckDB file that caches the last N months of base_events + job_data for downtime analysis. Relative paths resolve against CWD. For Docker set to an absolute path on a named volume. Atomically replaced on each daily refresh. Added by change `downtime-analysis-duckdb-cache`.
- `RESOURCE_HISTORY_DUCKDB_PATH`: Path to the persistent DuckDB file that caches the last N months of base_facts + oee_facts. Relative paths resolve against CWD (same as QUERY_SPOOL_DIR). For Docker set to an absolute path on a named volume. File is ~15MB; atomically replaced on each daily refresh. Added by change `resource-history-perf`.
- `RESOURCE_VIEW_CACHE_TTL`: TTL in seconds for the view-result cache in `apply_view()`. Derived numbers (KPI, trend, heatmap, etc.) may be up to this many seconds stale within an already-warm dataset. Set to `0` to disable the view-result cache and always recompute from spool. Default 300 s (5 min). Added by change `resource-history-cache-fix`.

## Async Worker — Downtime Query

| name | scope | environments | required | secret | default | example | owner | validation | restart required | failure behavior |
|---|---|---|---:|---:|---|---|---|---|---:|---|
| DOWNTIME_ASYNC_ENABLED | feature-flag | all | no | no | true | true | application-team | true or false | yes | false = all downtime queries run synchronously regardless of date range |
| DOWNTIME_ASYNC_DAY_THRESHOLD | async | all | no | no | 30 | 30 | application-team | **Deprecated** (removal P5); positive integer ≥ 1; queries spanning ≥ this many calendar days use the async RQ path when DOWNTIME_ASYNC_ENABLED=true; migrate to `CostPolicy.day_threshold` via `classify_query_cost()` | yes | uses default 30 |
| DOWNTIME_WORKER_QUEUE | async | all | no | no | downtime-query | downtime-query | application-team | non-empty string; RQ queue name for the downtime worker process | yes | uses default "downtime-query" |
| DOWNTIME_JOB_TIMEOUT_SECONDS | async | all | no | no | 1800 | 1800 | application-team | positive integer (seconds); RQ job timeout for the downtime worker; must exceed the longest expected Oracle query duration | yes | uses default 1800 |

- `DOWNTIME_ASYNC_ENABLED`: Feature flag enabling the async RQ path for long downtime queries. When `false`, all `POST /api/downtime-analysis/query` calls run synchronously regardless of date span. Default `true`; set to `false` for emergency rollback without disabling the `DOWNTIME_BROWSER_DUCKDB` path. **Restart required** — module-level constant frozen at import. Added by change `downtime-rq-async`.
- `DOWNTIME_ASYNC_DAY_THRESHOLD`: **Deprecated** — will be removed in P5 (deprecate-2-minors policy). A runtime `DeprecationWarning` is emitted by `classify_query_cost()` when this var is present in `os.environ`. Warning text: `"DOWNTIME_ASYNC_DAY_THRESHOLD is deprecated and will be removed in a future minor release (deprecate-2-minors policy). Use CostPolicy.day_threshold via classify_query_cost() instead."` Migrate to `CostPolicy(day_threshold=30)` passed to `classify_query_cost()`. Number of calendar days at or above which a downtime query is dispatched via RQ (when `DOWNTIME_ASYNC_ENABLED=true`). Default `30`. Added by change `downtime-rq-async`; deprecated by `unified-query-core-infra`.
- `DOWNTIME_WORKER_QUEUE`: RQ queue name that `enqueue_job_dynamic()` routes downtime jobs to. Must match the `--queues` argument of the running downtime worker process. Default `"downtime-query"`. Added by change `downtime-rq-async`.
- `DOWNTIME_JOB_TIMEOUT_SECONDS`: Maximum seconds a single RQ downtime job may run before the worker kills it. Must be set above the worst-case Oracle fetch duration for a 730-day range (≈ 1200 s observed on large datasets; default 1800 s provides 50% headroom). Added by change `downtime-rq-async`.

**Worker env-var parity:** The `mes-dashboard-downtime-worker.service` systemd unit MUST export the same `DOWNTIME_*` and DuckDB env set as gunicorn (at minimum: `DOWNTIME_BROWSER_DUCKDB`, `DOWNTIME_ASYNC_ENABLED`, `DOWNTIME_ANALYSIS_DUCKDB_PATH`, `DOWNTIME_ANALYSIS_CACHE_TTL`). Env-var drift between the worker unit and gunicorn silently changes which acquisition path runs (DuckDB prewarm vs Oracle fallback), breaking AC-3 parity. Validate via deploy-time env comparison or the CI parquet-schema gate (see `contracts/ci/ci-gate-contract.md §downtime-rq-async Gate Compatibility Note`). Added by change `downtime-rq-async`.

## Async Worker — Hold History Query

| name | scope | environments | required | secret | default | example | owner | validation | restart required | failure behavior |
|---|---|---|---:|---:|---|---|---|---|---:|---|
| HOLD_ASYNC_ENABLED | feature-flag | all | no | no | true | true | application-team | true or false | yes | false = all hold-history queries run synchronously regardless of date range |
| HOLD_ASYNC_DAY_THRESHOLD | async | all | no | no | 90 | 90 | application-team | **Deprecated** (removal P5); positive integer ≥ 1; queries spanning ≥ this many calendar days use the async RQ path when HOLD_ASYNC_ENABLED=true; migrate to `CostPolicy.day_threshold` via `classify_query_cost()` | yes | uses default 90 |
| HOLD_WORKER_QUEUE | async | all | no | no | hold-history-query | hold-history-query | application-team | non-empty string; RQ queue name for the hold-history worker process | yes | uses default "hold-history-query" |
| HOLD_JOB_TIMEOUT_SECONDS | async | all | no | no | 1800 | 1800 | application-team | positive integer (seconds); RQ job timeout for the hold-history worker; must exceed the longest expected Oracle query duration | yes | uses default 1800 |

- `HOLD_ASYNC_ENABLED`: Feature flag enabling the async RQ path for long hold-history queries. When `false`, all `POST /api/hold-history/query` calls run synchronously regardless of date span. Default `true`; set to `false` for emergency rollback. **Restart required** — module-level constant frozen at import. Added by change `hold-history-rq-async`.
- `HOLD_ASYNC_DAY_THRESHOLD`: **Deprecated** — will be removed in P5 (deprecate-2-minors policy). A runtime `DeprecationWarning` is emitted by `classify_query_cost()` when this var is present in `os.environ`. Warning text: `"HOLD_ASYNC_DAY_THRESHOLD is deprecated and will be removed in a future minor release (deprecate-2-minors policy). Use CostPolicy.day_threshold via classify_query_cost() instead."` Migrate to `CostPolicy(day_threshold=90)`. Number of calendar days at or above which a hold-history query is dispatched via RQ (when `HOLD_ASYNC_ENABLED=true`). Default `90`. Added by change `hold-history-rq-async`; deprecated by `unified-query-core-infra`.
- `HOLD_WORKER_QUEUE`: RQ queue name that `enqueue_job_dynamic()` routes hold-history jobs to. Must match the `--queues` argument of the running hold-history worker process. Default `"hold-history-query"`. Added by change `hold-history-rq-async`.
- `HOLD_JOB_TIMEOUT_SECONDS`: Maximum seconds a single RQ hold-history job may run before the worker kills it. Default 1800 s. Added by change `hold-history-rq-async`.

**Worker env-var parity:** The `mes-dashboard-hold-history-worker.service` systemd unit MUST export the same `HOLD_*` env set as gunicorn (at minimum: `HOLD_ASYNC_ENABLED`, `HOLD_ASYNC_DAY_THRESHOLD`, `HOLD_WORKER_QUEUE`, `HOLD_JOB_TIMEOUT_SECONDS`). Env-var drift silently changes query routing. Added by change `hold-history-rq-async`.

## Async Worker — Resource History Query

| name | scope | environments | required | secret | default | example | owner | validation | restart required | failure behavior |
|---|---|---|---:|---:|---|---|---|---|---:|---|
| RESOURCE_ASYNC_ENABLED | feature-flag | all | no | no | true | true | application-team | true or false | yes | false = all resource-history queries run synchronously regardless of date range |
| RESOURCE_ASYNC_DAY_THRESHOLD | async | all | no | no | 90 | 90 | application-team | **Deprecated** (removal P5); positive integer ≥ 1; queries spanning ≥ this many calendar days use the async RQ path when RESOURCE_ASYNC_ENABLED=true; migrate to `CostPolicy.day_threshold` via `classify_query_cost()` | yes | uses default 90 |
| RESOURCE_WORKER_QUEUE | async | all | no | no | resource-history-query | resource-history-query | application-team | non-empty string; RQ queue name for the resource-history worker process | yes | uses default "resource-history-query" |
| RESOURCE_JOB_TIMEOUT_SECONDS | async | all | no | no | 1800 | 1800 | application-team | positive integer (seconds); RQ job timeout for the resource-history worker; must exceed the longest expected Oracle query duration | yes | uses default 1800 |

- `RESOURCE_ASYNC_ENABLED`: Feature flag enabling the async RQ path for long resource-history queries. When `false`, all `POST /api/resource/history/query` calls run synchronously regardless of date span. Default `true`; set to `false` for emergency rollback. **Restart required** — module-level constant frozen at import. Added by change `resource-history-rq-async`.
- `RESOURCE_ASYNC_DAY_THRESHOLD`: **Deprecated** — will be removed in P5 (deprecate-2-minors policy). A runtime `DeprecationWarning` is emitted by `classify_query_cost()` when this var is present in `os.environ`. Warning text: `"RESOURCE_ASYNC_DAY_THRESHOLD is deprecated and will be removed in a future minor release (deprecate-2-minors policy). Use CostPolicy.day_threshold via classify_query_cost() instead."` Migrate to `CostPolicy(day_threshold=90)`. Number of calendar days at or above which a resource-history query is dispatched via RQ (when `RESOURCE_ASYNC_ENABLED=true`). Default `90`. Added by change `resource-history-rq-async`; deprecated by `unified-query-core-infra`.
- `RESOURCE_WORKER_QUEUE`: RQ queue name that `enqueue_job_dynamic()` routes resource-history jobs to. Must match the `--queues` argument of the running resource-history worker process. Default `"resource-history-query"`. Added by change `resource-history-rq-async`.
- `RESOURCE_JOB_TIMEOUT_SECONDS`: Maximum seconds a single RQ resource-history job may run before the worker kills it. Default 1800 s. Added by change `resource-history-rq-async`.

**Worker env-var parity:** The `mes-dashboard-resource-history-worker.service` systemd unit MUST export the same `RESOURCE_*` env set as gunicorn (at minimum: `RESOURCE_ASYNC_ENABLED`, `RESOURCE_ASYNC_DAY_THRESHOLD`, `RESOURCE_WORKER_QUEUE`, `RESOURCE_JOB_TIMEOUT_SECONDS`). Env-var drift silently changes query routing. Added by change `resource-history-rq-async`.

## Async Worker — Reject History Query (Threshold Deprecation)

| name | scope | environments | required | secret | default | example | owner | validation | restart required | failure behavior |
|---|---|---|---:|---:|---|---|---|---|---:|---|
| REJECT_ASYNC_DAY_THRESHOLD | async | all | no | no | 10 | 10 | application-team | **Deprecated** (removal P5); positive integer ≥ 1; reject queries spanning > this many calendar days use the async RQ path; migrate to `CostPolicy.day_threshold` via `classify_query_cost()` | yes | uses default 10 |

- `REJECT_ASYNC_DAY_THRESHOLD`: **Deprecated** — will be removed in P5 (deprecate-2-minors policy). A runtime `DeprecationWarning` is emitted by `classify_query_cost()` when this var is present in `os.environ`. Warning text: `"REJECT_ASYNC_DAY_THRESHOLD is deprecated and will be removed in a future minor release (deprecate-2-minors policy). Use CostPolicy.day_threshold via classify_query_cost() instead."` Migrate to `CostPolicy(day_threshold=10)`. Queries spanning more than this many calendar days use the RQ async path. Default `10`. Previously undocumented in this contract; documented here as part of deprecation by change `unified-query-core-infra`.

## Batch Query Engine — Row-Count Chunking

| name | scope | environments | required | secret | default | example | owner | validation | restart required | failure behavior |
|---|---|---|---:|---:|---|---|---|---|---:|---|
| USE_ROW_COUNT_CHUNKING | batch-engine | all | no | no | false | false | application-team | true or false | yes | uses date-range path (default) |
| BATCH_QUERY_ROWS_PER_CHUNK | batch-engine | all | no | no | 50000 | 50000 | application-team | positive integer; must be >= 1 | yes | uses default 50000 |

- `USE_ROW_COUNT_CHUNKING`: When `false` (default), all 7 large-query services use the existing date-range chunking path — no behavior change on deployment. When `true`, activates `decompose_by_row_count()`: each service issues a `SELECT COUNT(*)` first, then fetches rows via `ROW_NUMBER() OVER (ORDER BY <key>) AS rn` + `rn BETWEEN :start_row AND :end_row`. Per-service ORDER BY keys are deterministic and fully tie-breaking (see business-rules.md BQE-03). Must not be set to `true` in production until flag=true parity tests pass (ci-gates.md §Promotion Policy). Added by change `batch-rowcount-unification`.
- `BATCH_QUERY_ROWS_PER_CHUNK`: Maximum rows per chunk when `USE_ROW_COUNT_CHUNKING=true`. Controls the `end_row - start_row + 1` window in each `rn BETWEEN :start_row AND :end_row` paged SQL. Default `50000`. Must be >= 1; values above DB_SLOW_POOL_SIZE × connection timeout may cause individual chunk timeouts. Added by change `batch-rowcount-unification`.

## Engine Parallelism — Hold / Job / MSD

| name | scope | environments | required | secret | default | example | owner | validation | restart required | failure behavior |
|---|---|---|---:|---:|---|---|---|---|---:|---|
| HOLD_ENGINE_PARALLEL | batch-engine | all | no | no | 1 | 2 | application-team | positive integer; must not exceed DB_SLOW_POOL_SIZE (code default: dev=2, prod=5) | yes | uses default 1 (sequential) |
| JOB_ENGINE_PARALLEL | batch-engine | all | no | no | 1 | 2 | application-team | positive integer; must not exceed DB_SLOW_POOL_SIZE (code default: dev=2, prod=5) | yes | uses default 1 (sequential) |
| MSD_ENGINE_PARALLEL | batch-engine | all | no | no | 1 | 2 | application-team | positive integer; must not exceed DB_SLOW_POOL_SIZE (code default: dev=2, prod=5) | yes | uses default 1 (sequential) |

- `HOLD_ENGINE_PARALLEL` / `JOB_ENGINE_PARALLEL` / `MSD_ENGINE_PARALLEL`: Maximum parallel Oracle connections for the respective service's BatchQueryEngine. Hard ceiling: must not exceed `DB_SLOW_POOL_SIZE` (env-configurable; code default: dev=2, prod=5 per `settings.py`). A value above the ceiling silently saturates the slow pool and causes connection timeouts for other services. Default `1` (sequential) matches pre-existing behavior. Added by change `batch-rowcount-unification`.

## Hold Overview Export

| name | scope | environments | required | secret | default | example | owner | validation | restart required | failure behavior |
|---|---|---|---:|---:|---|---|---|---|---:|---|
| HOLD_OVERVIEW_EXPORT_MAX_ROWS | hold-overview | all | no | no | 10000 | 10000 | application-team | positive integer >= 1 | no | uses default 10000 |

- `HOLD_OVERVIEW_EXPORT_MAX_ROWS`: Maximum number of rows returned by `GET/POST /api/hold-overview/lots` when `export=true`. The per-request cap is enforced in the service layer (both snapshot and Oracle paths) so the cap applies regardless of which path executes. Exports silently truncate when the filtered hold set exceeds this cap; raise the cap and add a UI warning banner if truncation becomes a production concern. Default `10000`. Added by change `hold-overview-export-csv`.


## Async Worker — EAP ALARM Spool

| name | scope | environments | required | secret | default | example | owner | validation | restart required | failure behavior |
|---|---|---|---:|---:|---|---|---|---|---:|---|
| EAP_ALARM_WORKER_QUEUE | async | all | no | no | eap-alarm-query | eap-alarm-query | application-team | non-empty string; RQ queue name for the EAP ALARM worker | yes | uses default |
| EAP_ALARM_JOB_TIMEOUT_SECONDS | async | all | no | no | 1800 | 1800 | application-team | positive integer (seconds); must exceed longest Oracle query duration | yes | uses default 1800 |
| EAP_ALARM_SPOOL_TTL | cache | all | no | no | 72000 | 72000 | application-team | positive integer (seconds); minimum 3600 | yes | uses default 72000 |
| EAP_ALARM_SPOOL_DIR | storage | all | no | no | tmp/query_spool/eap_alarm | /var/lib/mes/eap_alarm | application-team | directory path (relative resolved to CWD; use absolute for Docker) | yes | uses default path |

- `EAP_ALARM_WORKER_QUEUE`: RQ queue name for EAP ALARM spool jobs. Must match `--queues` arg of the running EAP ALARM worker. Default `"eap-alarm-query"`. Added by change `eap-alarm-analysis`.
- `EAP_ALARM_JOB_TIMEOUT_SECONDS`: Max seconds a single EAP ALARM RQ job may run. Default 1800 s. Added by change `eap-alarm-analysis`.
- `EAP_ALARM_SPOOL_TTL`: Redis spool metadata TTL for EAP ALARM queries. Default 72000 s (20h). Added by change `eap-alarm-analysis`.
- `EAP_ALARM_SPOOL_DIR`: Directory for EAP ALARM parquet spool files. Relative paths resolve against CWD. Default `tmp/query_spool/eap_alarm`. Added by change `eap-alarm-analysis`.

**Worker env-var parity:** The `mes-dashboard-eap-alarm-worker.service` systemd unit MUST export the same `EAP_ALARM_*` env set as gunicorn.

## Unified Query Infrastructure — DuckDB Job Temp Directory

| name | scope | environments | required | secret | default | example | owner | validation | restart required | failure behavior |
|---|---|---|---:|---:|---|---|---|---|---:|---|
| DUCKDB_JOB_DIR | storage | all | no | no | tmp/duckdb_jobs | /var/lib/mes/duckdb_jobs | application-team | directory path (relative resolved to CWD; use absolute for Docker) | yes | uses default path |

- `DUCKDB_JOB_DIR`: Directory for transient per-job DuckDB files created by `BaseChunkedDuckDBJob`. Each job writes a `{namespace}/{job_id}.duckdb` file here during execution; the file is deleted in a `finally` block on job completion or failure (D7). Crash survivors are reaped by TTL orphan cleanup. Default `tmp/duckdb_jobs` (sibling of `QUERY_SPOOL_DIR` default `tmp/query_spool`; the default is computed as `{QUERY_SPOOL_DIR}/../duckdb_jobs`). Use an absolute path on a named volume in Docker. **Must not overlap with `QUERY_SPOOL_DIR`** — job-temp files are transient and must be physically separated from the persistent canonical parquet spool to prevent TTL/cleanup cross-contamination. Restart required — module-level constant in `base_chunked_duckdb_job.py` is frozen at import. Added by change `unified-query-core-infra`.

## Observability / Circuit Breaker

| name | scope | environments | required | secret | default | example | owner | validation | restart required | failure behavior |
|---|---|---|---:|---:|---|---|---|---|---:|---|
| CIRCUIT_BREAKER_ENABLED | observability | all | no | no | true | true | platform-team | true or false | no | — |
| CIRCUIT_BREAKER_FAILURE_THRESHOLD | observability | all | no | no | 5 | 5 | platform-team | positive integer | no | — |
| CIRCUIT_BREAKER_FAILURE_RATE | observability | all | no | no | 0.5 | 0.5 | platform-team | 0.0-1.0 | no | — |
| CIRCUIT_BREAKER_RECOVERY_TIMEOUT | observability | all | no | no | 30 | 30 | platform-team | positive integer (seconds) | no | — |
| SLOW_QUERY_THRESHOLD | observability | all | no | no | 5.0 | 5.0 | platform-team | positive float (seconds) | no | — |
| LOG_STORE_ENABLED | observability | all | no | no | true | true | platform-team | true or false | no | — |
| LOG_SQLITE_PATH | observability | all | no | no | logs/admin_logs.sqlite | logs/admin_logs.sqlite | platform-team | writable path | no | logging 停用 |
| LOG_SQLITE_RETENTION_DAYS | observability | all | no | no | 7 | 7 | platform-team | positive integer | no | — |

---

## Public Frontend Env Policy

Variables such as `VITE_`, `NEXT_PUBLIC_`, and `PUBLIC_` are browser-exposed. Never store secrets in them.

## Secret Policy

- 所有 `secret: yes` 的變數只存在 `.env`（未 commit 到 git）。
- Docker/CI 環境透過 secrets manager 或 env injection 注入，不硬編碼。
- **禁止** commit `.env`（`.gitignore` 已設定）。
- `SECRET_KEY` 在 production 必須使用高熵隨機字串（≥32 bytes）。
- `REGISTER_INTERNAL_METRICS` / `INTERNAL_METRICS_ENABLED` 在 production 必須為 False/0。

## Deployment Sync Policy

1. 新增或移除 env 變數時，必須同步更新此契約（同一 PR）。
2. 改變變數預設值或語意時，視為 breaking change，走 deprecate-2-minors 流程。
3. Production 部署前需核對此清單，確認所有 `required: yes` 的變數均已設定。

## Validation Notes

- `FLASK_DEBUG=1` 在 production 是嚴重安全問題：啟動時 `_validate_production_security_settings()` 會拒絕。
- `SECRET_KEY` 過短（< 32 bytes）：`_resolve_secret_key()` 會記錄 warning。
- `DB_HOST` / `DB_SERVICE` 空值：app factory 啟動時即失敗，不會延遲到首次查詢。

## CHANGELOG

## [env 1.0.18] — 2026-06-19
### Added
- material-trace-streaming-migration: `MATERIAL_TRACE_USE_UNIFIED_JOB` (optional, default `off`, restart required) — feature flag selecting unified `MaterialTraceJob` streaming Arrow→DuckDB path vs legacy `pd.concat(chunks)` + post-hoc `_check_memory_guard()` path (P4 migration). `always_async=True`; `sync_fallback_allowed=False`; RQ unavailable → 503. Semaphore role updated: `global_concurrency.acquire_heavy_query_slot` semantics shift from "protect sync path" to "limit RQ concurrency to Oracle" (no code change). Additive; no existing flags changed.

## [env 1.0.17] — 2026-06-19
### Added
- resource-history-migration: `RESOURCE_HISTORY_USE_UNIFIED_JOB` (optional, default `off`, restart required) — feature flag selecting unified `ResourceHistoryBaseJob` + `ResourceHistoryOeeJob` path (P3 migration) vs legacy `export_csv` Oracle read + iterrows path. `always_async=True`; `sync_fallback_allowed=False`; degraded → 503. Additive; no existing flags changed.

## [env 1.0.16] — 2026-06-19
### Added
- production-reject-history-migration: Added `PRODUCTION_HISTORY_USE_UNIFIED_JOB` (default `off`) and `REJECT_HISTORY_USE_UNIFIED_JOB` (default `off`) feature flags for P2 BaseChunkedDuckDBJob migration. Both flags are module-level constants frozen at import (restart required); `always_async=False` for both job types; `sync_fallback_allowed=True`. Additive; no existing flags changed.

