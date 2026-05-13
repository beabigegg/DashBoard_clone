---
contract: env
summary: Environment variable inventory, secret handling, and deployment sync policy.
owner: platform-team
surface: runtime-config
schema-version: 1.0.1
last-changed: 2026-05-13
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

## Cache Tuning — Resource History

| name | scope | environments | required | secret | default | example | owner | validation | restart required | failure behavior |
|---|---|---|---:|---:|---|---|---|---|---:|---|
| RESOURCE_HISTORY_HISTORICAL_TTL | cache | all | no | no | 86400 | 86400 | application-team | positive integer (seconds); minimum 3600 | yes | uses default 86400 |
| RESOURCE_HISTORY_PREWARM_MONTHS | cache | all | no | no | 3 | 3 | application-team | positive integer 1–12; 0 disables pre-warm | yes | uses default 3 |

- `RESOURCE_HISTORY_HISTORICAL_TTL`: Redis TTL for resource-history queries where `end_date < today − 2 days`. Historical data is immutable; default 86400s (24h) vs the general 2h TTL for recent queries. Added by change `resource-history-perf`.
- `RESOURCE_HISTORY_PREWARM_MONTHS`: Number of calendar months of resource-history data to pre-warm into Redis on service startup. Pre-warm runs as a background thread after gunicorn workers are ready; `0` disables pre-warm entirely. Default 3 months. Oracle memory budget confirmed by spec-architect before deploying with values > 3. Added by change `resource-history-perf`.

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
