# SDD — MES Dashboard 系統設計文件

> 版本：1.0 | 日期：2026-04-08 | 狀態：正式版

---

## 1. 系統整體說明

### 概述

本系統為全端 Web 應用，提供半導體製造廠各部門工程師查詢 MES（Manufacturing Execution System）生產數據的自助報表平台。  
後端以 Flask + Gunicorn 提供 REST API，前端為 Vue 3 + Vite 多頁應用，同源部署（單一 Port）。  
資料庫為唯讀存取 Oracle 生產資料庫，並以 Redis + DuckDB 多層快取降低 Oracle 負載、加速查詢回應。

### 核心流程

```
使用者 (瀏覽器)
  → Portal Shell SPA 路由切換
  → 各報表頁面 (Vue 3 SFC)
  → REST API 呼叫 (api.js)
  → Flask Blueprint 路由
  → Service 層（快取命中 → 直接回傳；快取未中 → 查 Oracle）
  → Oracle 19c (唯讀查詢)
  → Redis 快取寫入
  → 結果回傳前端
```

重查詢（長時間查詢）流程：

```
前端提交查詢
  → /api/xxx/query POST
  → 任務進入 RQ 佇列
  → 回傳 job_id (202 Accepted)
  → 前端輪詢 /api/xxx/job/<job_id>
  → RQ Worker 執行完成 → 結果寫入 Redis/Spool
  → 前端取得結果
```

### 專案類型

- 類型：全端 Web 應用（後端 API + 前端 SPA）
- 後端框架：Flask 3.x
- 前端框架：Vue 3 + Vite
- 資料庫：Oracle 19c（唯讀）
- 快取：Redis 7.x + 程序級 LRU + DuckDB（後端）+ DuckDB-WASM（前端）

---

## 2. 系統架構圖

```
+-----------------------------------------------------------------------------------+
|                              使用者瀏覽器                                          |
|  Portal Shell (Vue Router SPA)  +  各報表頁面 (Vue 3 SFC)  +  DuckDB-WASM        |
+---------------------------+----------------------------------------------------+--+
                            | HTTP (同源, port 8080)
                            v
+---------------------------+----------------------------------------------------+
|                         Gunicorn (WSGI, multi-worker)                          |
|  Worker 1  |  Worker 2  |  Worker 3  |  Worker 4  (PRD 4 workers)              |
+---------------------------+----------------------------------------------------+
                            |
              +-------------+-------------------+
              |             |                   |
              v             v                   v
    +------------------+  +------------------+  +------------------+
    |   Flask App      |  |   RQ Workers     |  |   Watchdog       |
    |  (20 Blueprints) |  |  (5 佇列)        |  |  (worker_watchdog|
    |  routes/         |  |  - trace-events  |  |   .py)           |
    |  services/       |  |  - reject-query  |  +------------------+
    |  core/           |  |  - msd-analysis  |
    |  sql/            |  |  - prod-history  |
    +--------+---------+  |  - yield-alert   |
             |            +--------+---------+
     +-------+-------+            |
     |               |      ------+------
     v               v      |           |
+--------+     +----------+ v           v
| Redis  |     |  Oracle  | Redis     Oracle
|  7.x   |     |   19c    | (快取)    (慢查詢)
| 多層快取|     | (唯讀)   |
| Parquet|     | SQL 模板 |
| DF 序列|     | 查詢     |
+--------+     +----------+
```

### 快取分層說明

```
L0: 程序級 LRU Cache (bounded, in-memory, TTL 30s)
    ↓ miss
L1: Redis Cache (DataFrame Parquet 序列化, TTL 可配置)
    ↓ miss
L2: DuckDB SQL Runtime (Parquet spool 上執行 SQL, reject/yield)
    ↓ miss
L3: Oracle 19c 查詢
    ↓ 結果
    → 寫入 L1 (Redis)
    → 依需求寫入 L2 (Spool Parquet)
```

---

## 3. 技術選型

### 採用技術（後端）

| 技術 | 版本 | 用途 | 選用理由 |
|------|------|------|----------|
| Flask | 3.x | Web 框架 | 輕量，Blueprint 模組化，適合多報表 API |
| Gunicorn | 21.x+ | WSGI 伺服器 | 多 Worker 並發，Linux 生產環境標準選擇 |
| SQLAlchemy | 2.x | 連線池管理 | 提供可靠的 Oracle 連線池，支援雙池（主查詢/慢查詢） |
| oracledb | 2.x+ | Oracle 驅動 | Oracle 官方 Python 驅動，thin mode 免安裝 client |
| Redis | 7.x | 多層快取 | 高性能，支援 DataFrame Parquet 序列化快取 |
| RQ (Redis Queue) | 1.16+ | 非同步任務佇列 | 輕量，基於 Redis，適合重查詢任務隔離 |
| DuckDB | 1.x | 快取 SQL Runtime | 直接查 Parquet 檔，無需全部載入記憶體 |
| Pandas + PyArrow | 2.3 / 17.x+ | 數據處理與序列化 | DataFrame 操作 + Parquet 壓縮序列化 |
| python-dotenv | 1.x | 環境變數載入 | 標準 .env 管理 |
| psutil | 5.x+ | 系統監控 | RSS 記憶體監控，Worker 記憶體防護 |

### 採用技術（前端）

| 技術 | 版本 | 用途 | 選用理由 |
|------|------|------|----------|
| Vue 3 | 3.5 | UI 框架 | Composition API + SFC，元件化報表頁面 |
| Vue Router | 4.6 | Portal Shell SPA 路由 | no-iframe 路由切換，單 Port 架構 |
| Vite | 6.3 | 多頁打包 | 19 個 entry point，快速建置，HMR 開發體驗 |
| ECharts + vue-echarts | 6.0 / 8.0 | 圖表庫 | 豐富的工業圖表類型，支援 tree-shaking |
| DuckDB-WASM | 1.33+ | 瀏覽器端 SQL | view compute offload，減少 server 負載 |
| Tailwind CSS | 3.4 | 樣式框架 | 設計 token 統一管理，CSS 體積可控 |
| @vueuse/core | 14.x | 工具函式庫 | 常用 Composable（useEventListener, useThrottle 等） |

### 設計決策（未採用技術）

| 技術 | 未採用原因 |
|------|-----------|
| ORM（SQLAlchemy model） | 唯讀查詢為主，SQL 模板可讀性更高；Oracle 視圖/函式不適合 ORM mapping |
| iframe 前端架構 | Portal Shell 全面遷移至 Vue Router no-iframe，避免跨 frame 通訊與 Session 問題 |
| Flask-CORS 套件 | 同源架構無需 CORS；透過自訂 `after_request` 處理安全標頭 |
| WebSocket | 重查詢輪詢已足夠，避免 WebSocket 連線管理複雜度 |
| JWT 認證 | 使用 server-side session，符合既有 LDAP 認證流程 |

---

## 4. 模組劃分

### 模組總覽

| 模組 | 路徑 | 職責 |
|------|------|------|
| 路由層 | `src/mes_dashboard/routes/` | 20 個 Blueprint；接收請求、參數驗證、呼叫 service、統一回應格式 |
| 服務層 | `src/mes_dashboard/services/` | 45+ 模組；商業邏輯、快取策略、RQ 任務管理 |
| 核心基礎設施 | `src/mes_dashboard/core/` | 28 個模組；資料庫、Redis、Circuit Breaker、Rate Limit、CSRF、權限、記憶體防護 |
| SQL 模板層 | `src/mes_dashboard/sql/` | 85+ SQL 檔案；依功能分目錄管理，loader/builder/filters 統一載入 |
| 設定層 | `src/mes_dashboard/config/` | 環境設定、常數、欄位契約、工作中心群組 |
| 前端核心 | `frontend/src/core/` | REST API 客戶端、DuckDB-WASM 客戶端、欄位契約、導覽結構 |
| 前端報表頁面 | `frontend/src/<page>/` | 19 個報表/管理頁面，各為獨立 Vite entry point |

### 模組依賴關係

```
routes/
  └─ services/
       ├─ core/database.py      (Oracle 連線池)
       ├─ core/redis_client.py  (Redis 客戶端)
       ├─ sql/loader.py         (SQL 模板載入)
       └─ core/response.py      (統一回應格式)

core/
  ├─ circuit_breaker.py  (保護 Oracle 連線)
  ├─ rate_limit.py       (API 頻率限制)
  ├─ csrf.py             (CSRF Token 驗證)
  ├─ permissions.py      (Admin 角色檢查)
  ├─ worker_memory_guard.py  (Worker RSS 監控)
  └─ resilience.py       (韌性診斷)
```

### 關鍵模組說明

#### Flask 應用工廠（`src/mes_dashboard/app.py`）
- 職責：建立 Flask app，登錄所有 Blueprint，設定中間件（CSRF、安全標頭、Session）
- 重要函式：`create_app(config_class)` — 應用工廠模式，支援測試注入

#### 快取系統（`core/cache.py`, `core/cache_updater.py`, `services/*_dataset_cache.py`）
- 三層策略：程序級 LRU → Redis Parquet → Oracle 查詢
- `WipCache`、`ResourceCache`、`RejectDatasetCache`、`HoldDatasetCache` 等各自管理其快取生命週期

#### 非同步任務（`services/*_job_service.py`）
- 統一接口：`submit_job()` → RQ enqueue → 回傳 `job_id`
- `get_job_status(job_id)` → 查詢 Redis Job 狀態
- 5 個專用佇列（trace-events / reject-query / msd-analysis / production-history / yield-alert）

#### Circuit Breaker（`core/circuit_breaker.py`）
- 狀態機：`CLOSED → OPEN（失敗率超標）→ HALF_OPEN（恢復冷卻後）→ CLOSED`
- 雪崩保護：Oracle 不穩定時自動切斷，回傳 503 而非讓請求積壓

#### Worker 記憶體防護（`core/worker_memory_guard.py`）
- RSS 監控：`psutil` 定期採樣，超 warn_ratio → 觸發 GC，超 hard_ratio → 強制 Worker 重啟
- 配合 Watchdog（`scripts/worker_watchdog.py`）守護 Gunicorn 進程

---

## 5. 介面設計

### 主要頁面路由（前端）

| 路徑 | 功能 | Vue Entry |
|------|------|-----------|
| `/wip-overview` | WIP 即時概況 | `src/wip-overview/` |
| `/wip-detail` | WIP 明細查詢 | `src/wip-detail/` |
| `/hold-detail` | Hold 明細分析 | `src/hold-detail/` |
| `/hold-overview` | Hold 即時概況 | `src/hold-overview/` |
| `/hold-history` | Hold 歷史績效 | `src/hold-history/` |
| `/resource` | 設備即時概況 | `src/resource-status/` |
| `/resource-history` | 設備歷史績效 | `src/resource-history/` |
| `/qc-gate` | QC-GATE 即時狀態 | `src/qc-gate/` |
| `/mid-section-defect` | 中段不良追溯 | `src/mid-section-defect/` |
| `/reject-history` | 不良歷史分析 | `src/reject-history/` |
| `/yield-alert-center` | 良率警示中心 | `src/yield-alert-center/` |
| `/material-trace` | 材料追溯 | `src/material-trace/` |
| `/tables` | 數據表查詢 | `src/tables/` |
| `/job-query` | 設備維修查詢 | `src/job-query/` |
| `/query-tool` | 批次追蹤工具 | `src/query-tool/` |
| `/production-history` | 生產歷史分析 | `src/production-history/` |
| `/admin-dashboard` | 統一管理儀表板 | `src/admin-dashboard/` |
| `/admin/performance` | 效能監控儀表板 | `src/admin-performance/` |
| `/admin-user-usage-kpi` | 使用者用量 KPI | `src/admin-user-usage-kpi/` |

### 主要 API 端點

#### 認證

| 方法 | 路徑 | 說明 | 需驗證 |
|------|------|------|--------|
| POST | `/api/auth/login` | LDAP 登入 | 否 |
| POST | `/api/auth/logout` | 登出 | 是 |
| GET | `/api/auth/me` | 取得當前使用者資訊 | 是 |
| GET | `/api/auth/heartbeat` | Session 保活 | 是 |

#### 健康檢查

| 方法 | 路徑 | 說明 | 需驗證 |
|------|------|------|--------|
| GET | `/health` | 系統健康摘要 | 否 |
| GET | `/health/deep` | 深度健康診斷 | 否 |

#### WIP

| 方法 | 路徑 | 說明 | 需驗證 |
|------|------|------|--------|
| GET | `/api/wip/overview` | WIP 概況矩陣 | 是 |
| GET | `/api/wip/detail` | WIP 明細（分頁） | 是 |
| GET | `/api/wip/autocomplete` | 批號 Autocomplete | 是 |

#### 不良歷史（含非同步）

| 方法 | 路徑 | 說明 | 需驗證 |
|------|------|------|--------|
| POST | `/api/reject-history/query` | 提交查詢（同步/非同步自動判斷） | 是 |
| GET | `/api/reject-history/job/<job_id>` | 輪詢非同步任務狀態 | 是 |
| GET | `/api/reject-history/list` | 查詢結果清單 | 是 |
| GET | `/api/reject-history/options` | 篩選選項 | 是 |
| GET | `/api/reject-history/trend` | 趨勢圖數據 | 是 |
| GET | `/api/reject-history/batch-pareto` | Pareto 分析（批次版） | 是 |
| GET | `/api/reject-history/export` | 匯出 Excel | 是 |

#### 異常偵測（Analytics）

| 方法 | 路徑 | 說明 | 需驗證 |
|------|------|------|--------|
| GET | `/api/analytics/anomaly-summary` | 異常偵測摘要 | 是 |
| GET | `/api/analytics/equipment-deviation` | 設備稼動異常 | 是 |
| GET | `/api/analytics/reject-spikes` | 不良率突增 | 是 |
| GET | `/api/analytics/yield-anomalies` | 良率異常 | 是 |
| GET | `/api/analytics/hold-outliers` | Hold 離群 | 是 |
| POST | `/api/analytics/recalculate` | 手動觸發重新計算（Admin） | Admin |

#### AI 查詢

| 方法 | 路徑 | 說明 | 需驗證 |
|------|------|------|--------|
| POST | `/api/ai/query` | AI 智能查詢（Text2SQL/Function/Agent） | 是 |

#### 管理（Admin）

| 方法 | 路徑 | 說明 | 需驗證 |
|------|------|------|--------|
| GET | `/api/system-status` | 系統狀態摘要 | Admin |
| GET | `/api/metrics` | 效能指標 | Admin |
| GET | `/api/logs` | 應用日誌 | Admin |
| POST | `/api/worker/restart` | 重啟 Worker | Admin |
| GET | `/api/user-usage-kpi` | 使用者用量 KPI | Admin |

### 統一回應格式

成功回應：
```json
{ "status": "ok", "data": { ... } }
```

分頁回應：
```json
{ "status": "ok", "data": [...], "total": 1234, "page": 1, "per_page": 50 }
```

非同步任務提交（202）：
```json
{ "status": "ok", "job_id": "abc123", "message": "查詢已進入佇列" }
```

錯誤回應：
```json
{ "status": "error", "message": "錯誤說明", "code": "ERROR_CODE" }
```

---

## 6. 資料庫設計

### 資料庫說明

本系統以唯讀方式存取外部 Oracle 19c MES 資料庫，不建立、不修改任何資料表。  
所有查詢均透過 `src/mes_dashboard/sql/` 目錄下的 SQL 模板執行，由 `sql/loader.py` 載入、`sql/builder.py` 動態組裝條件。

**本地資料儲存：**

| 儲存 | 用途 | 路徑 |
|------|------|------|
| Redis | DataFrame 快取（Parquet 序列化）、RQ 任務佇列與狀態 | `redis://localhost:6379/0`（可配置） |
| SQLite（login_sessions） | 登入 Session 紀錄 | `logs/login_sessions.sqlite` |
| SQLite（admin_logs） | 管理操作日誌 | `logs/admin_logs.sqlite` |
| Parquet spool 檔案 | 重查詢結果暫存（查詢後 TTL 過期自動清除） | `tmp/query_spool/` |
| MySQL（選配） | 登入 Session + 日誌的持久化（多機共用） | 依 `MYSQL_OPS_*` 配置 |

### 主要 Oracle 視圖/表格（唯讀存取）

| 視圖/表格 | 用途 |
|----------|------|
| `DWH.DW_MES_LOT_V` | WIP / Hold / 篩選選項快取主視圖 |
| `DWH.DW_MES_SPEC_WORKCENTER_V` | 工作中心規格視圖 |
| MES reject / event 相關視圖 | 不良歷史、生產歷史查詢 |

實際 Oracle 物件清單由資料庫管理員維護，詳見 `contract/api_inventory.md`。

---

## 7. 環境設定

### 環境設定檔

| 檔案 | 用途 |
|------|------|
| `.env.example` | 環境變數模板，含 DEV/PRD 差異說明 |
| `.env` | 實際設定，不進版控 |
| `src/mes_dashboard/config/settings.py` | 讀取環境變數，提供 Config / DevelopmentConfig / ProductionConfig / TestingConfig |
| `gunicorn.conf.py` | Gunicorn 服務設定，讀取 `GUNICORN_*` 環境變數 |

### 必要環境變數

| 變數名 | 用途 | 必填 |
|--------|------|------|
| `FLASK_ENV` | 環境模式（development/production/testing） | 是 |
| `FLASK_DEBUG` | 除錯模式（0/1） | 是 |
| `SECRET_KEY` | Session 加密金鑰，生產環境必須設定 | 是 |
| `DB_HOST` | Oracle 資料庫主機 | 是 |
| `DB_PORT` | Oracle 連接埠（預設 1521） | 是 |
| `DB_SERVICE` | Oracle 服務名稱 | 是 |
| `DB_USER` | Oracle 使用者名稱 | 是 |
| `DB_PASSWORD` | Oracle 密碼 | 是 |
| `LDAP_API_URL` | LDAP 認證 API URL | 是 |
| `ADMIN_EMAILS` | 管理員 Email 清單（逗號分隔） | 是 |
| `CORS_ALLOWED_ORIGINS` | 允許的 CORS 來源（同源架構可留空） | 是 |
| `REDIS_URL` | Redis 連線字串 | 是（啟用 Redis 時） |
| `GUNICORN_BIND` | 服務監聽地址（取代 PORT，如 `0.0.0.0:8080`） | 是 |

### 條件式環境變數

| 變數名 | 用途 | 條件 |
|--------|------|------|
| `AI_API_KEY` | LLM API 金鑰 | AI 查詢功能啟用時 |
| `AI_API_URL` | LLM API 端點 | AI 查詢功能啟用時 |
| `MYSQL_OPS_HOST/USER/PASSWORD/DATABASE` | MySQL 連線資訊 | 啟用 MySQL 持久化時 |
| `LOCAL_AUTH_USERNAME/PASSWORD` | 本地認證帳密 | DEV 環境本地測試時 |

### DEV vs PRD 差異

主要差異在資源配置（同一份 `.env`，切換以下值）：

| 配置項目 | DEV | PRD |
|----------|-----|-----|
| `GUNICORN_WORKERS` | 2 | 4 |
| `GUNICORN_THREADS` | 4 | 6 |
| `DB_POOL_SIZE` | 5 | 6 |
| `REDIS_MAXMEMORY` | 512mb | 768mb |
| `WIP_CACHE_TTL_SECONDS` | 1800 | 2400 |
| `TRACE_ASYNC_CID_THRESHOLD` | 20000 | 15000 |
| `WORKER_RSS_LIMIT_MB` | 0（自動） | 2800 |

---

## 8. 部署方式

### 前置條件

- Python 3.11+（透過 Conda `mes-dashboard` 虛擬環境管理）
- Node.js 22+（建議由 Conda `environment.yml` 管理）
- Oracle Database 19c 連線
- Redis Server 7.x+

### 自動部署（推薦）

```bash
# 一鍵部署：建立 Conda 環境、安裝依賴、驗證連線、複製 .env
./scripts/deploy.sh

# 編輯環境設定
cp .env.example .env
nano .env

# 建置前端
cd frontend && npm ci && npm run build && cd ..

# 啟動所有服務（Gunicorn + Redis + RQ Workers + Watchdog）
./scripts/start_server.sh start
```

### 手動部署步驟

```bash
# 1. 建立 Conda 環境
conda env create -f environment.yml
conda activate mes-dashboard

# 2. 安裝後端依賴
pip install -r requirements.txt

# 3. 建置前端
cd frontend && npm ci && npm run build && cd ..

# 4. 設定環境變數
cp .env.example .env && nano .env

# 5. 啟動服務
./scripts/start_server.sh start
```

### Systemd 服務（Linux 生產環境）

`deploy/` 目錄提供 5 個 systemd service 設定檔：

| 服務檔 | 說明 |
|--------|------|
| `mes-dashboard.service` | Gunicorn 主服務 |
| `mes-dashboard-trace-worker.service` | RQ trace-events worker |
| `mes-dashboard-reject-worker.service` | RQ reject-query worker |
| `mes-dashboard-msd-worker.service` | RQ msd-analysis worker |
| `mes-dashboard-watchdog.service` | Worker Watchdog 守護進程 |

> Yield-alert 及 Production-history worker 可依需求加入類似的 service 設定。

### 服務管理指令

```bash
./scripts/start_server.sh start    # 啟動所有服務
./scripts/start_server.sh stop     # 停止所有服務
./scripts/start_server.sh restart  # 重啟所有服務
./scripts/start_server.sh status   # 查看服務狀態
./scripts/start_server.sh logs follow  # 即時查看日誌
```

---

## 9. 安全性考量

### 已實作防護

| 風險 | 防護方式 | 實作位置 |
|------|----------|----------|
| SQL Injection | SQLAlchemy 參數化查詢；DuckDB 內部路徑 quote 處理 | `sql/builder.py`, `services/*_runtime.py` |
| XSS | Vue 3 自動 template escape；全域 CSP 標頭 | `app.py:_register_security_headers()` |
| CSRF | CSRF Token（admin form + admin mutation API） | `core/csrf.py`, `app.py` |
| Session 劫持 | `SECRET_KEY` 加密 Session；HSTS；Secure Cookie | `config/settings.py`, `app.py` |
| 未授權存取 | LDAP 認證 + Admin 角色檢查；未驗證請求 → 401 | `core/permissions.py`, `routes/auth_routes.py` |
| 惡意輸入 | `MAX_JSON_BODY_BYTES=256KB` 限制請求大小 | `core/request_guard.py` |
| 資料庫雪崩 | Circuit Breaker（失敗率超標自動切斷） | `core/circuit_breaker.py` |
| API 濫用 | 高成本 API 頻率限制（in-process rate limit） | `core/rate_limit.py` |
| 容器 ID 爆炸 | LOT/WAFER 輸入筆數上限、萬用字元前綴長度限制 | `services/container_resolution_policy.py` |
| Worker OOM | RSS 投影監控，graduated response（warn→restrict→restart） | `core/worker_memory_guard.py` |

### 全域安全標頭（`app.py`）

```
Content-Security-Policy: ...（依 CSP_ALLOW_UNSAFE_EVAL 調整）
X-Frame-Options: SAMEORIGIN
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
Strict-Transport-Security: max-age=31536000; includeSubDomains（HTTPS only）
```

### 不適用項目

- 本系統唯讀存取 Oracle，無寫入資料庫功能，無 SQL injection 寫入風險
- 本系統無檔案上傳功能，無需防範惡意上傳

---

## 10. 維護與監控

### 常見維護操作

| 操作 | 方式 |
|------|------|
| 新增報表頁面 | `routes/` 新增 Blueprint，`services/` 新增服務，`sql/` 新增 SQL 模板，前端新增 Vite entry |
| 修改 SQL 查詢 | 修改 `src/mes_dashboard/sql/<功能>/` 下對應 SQL 檔，無需重啟服務（動態載入） |
| 調整快取 TTL | 修改 `.env` 中對應的 `*_TTL_SECONDS` 變數後重啟 |
| 清除 Redis 快取 | 透過 `/admin-dashboard` → Cache 分頁手動清除 |
| 強制重啟 Worker | 透過 `/admin-dashboard` → Worker 分頁重啟 |
| 查看系統日誌 | `./scripts/start_server.sh logs follow` 或 `/admin-dashboard` → Logs 分頁 |
| 更新前端 | 修改 `frontend/src/` 後執行 `npm run build`（前端靜態檔由 Flask 提供） |

### 監控端點

| 端點 | 說明 |
|------|------|
| `GET /health` | 系統健康摘要（快取狀態、DB 狀態、Worker 狀態） |
| `GET /health/deep` | 深度診斷（含連線池、Circuit Breaker 狀態、重啟 churn） |
| `GET /api/system-status` | 管理儀表板系統狀態（Admin） |
| `GET /api/metrics` | 效能指標（請求延遲分佈、查詢統計） |

### 已知限制

| 限制 | 說明 |
|------|------|
| Oracle 單點依賴 | 資料來源唯一，Oracle 不可用時所有查詢失敗（Circuit Breaker 保護，但無備援） |
| 前端 console.log | 26 個 `console.error/warn` 未透過 Vite drop 設定在生產建置時移除 |
| `PORT` 命名不一致 | 服務埠號透過 `GUNICORN_BIND` 配置（非標準 `PORT` 變數名稱） |
| `CORS_ALLOWED_ORIGINS` | 定義於 `.env.example` 但目前程式碼未讀取此變數，CORS 依賴同源架構 |
| 無獨立 dev/prod .env | DEV/PRD 差異以 inline 註解方式說明，切換需手動修改，容易出錯 |
| API 文件格式 | 現有 `contract/api_inventory.md` 為 Markdown 清冊，非 Swagger/OpenAPI 格式 |

### 技術債追蹤

- [ ] deploy.sh 改用 `npm ci` 取代 `npm install --no-audit`
- [ ] Vite build 設定加入 `drop: ['console']` 移除前端 console 語句
- [ ] 建立 `.env.development` / `.env.production` 分離環境設定
- [ ] `CORS_ALLOWED_ORIGINS` 需確認實際是否生效
- [ ] 考慮產生 OpenAPI 規格（從 `contract/api_inventory.md` 轉換）
