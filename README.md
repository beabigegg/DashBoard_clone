# MES Dashboard 報表系統

基於 Flask + Gunicorn + Redis + Vite 的 MES 數據報表查詢與可視化系統

> 專案主執行根目錄：`DashBoard_vite/`
> Portal Shell 全面採用 no-iframe 的 SPA route-view 架構。

---

## 專案狀態

### 報表頁面

| 功能 | 路由 | 狀態 |
|------|------|------|
| WIP 即時概況 | `/wip-overview` | ✅ 已完成 |
| WIP 明細查詢 | `/wip-detail` | ✅ 已完成 |
| Hold 明細分析 | `/hold-detail` | ✅ 已完成 |
| Hold 即時概況（Matrix + Lot 明細） | `/hold-overview` | ✅ 已完成 |
| Hold 歷史績效 Dashboard | `/hold-history` | ✅ 已完成 |
| 設備即時概況 | `/resource` | ✅ 已完成 |
| 設備歷史績效 | `/resource-history` | ✅ 已完成 |
| QC-GATE 即時狀態報表 | `/qc-gate` | ✅ 已完成 |
| 中段製程不良追溯分析 | `/mid-section-defect` | ✅ 已完成 |
| 不良歷史分析 Dashboard | `/reject-history` | ✅ 已完成 |
| 良率警示中心 | `/yield-alert-center` | ✅ 已完成 |
| 材料追溯查詢 | `/material-trace` | ✅ 已完成 |
| 數據表查詢工具 | `/tables` | ✅ 已完成 |
| 設備維修查詢 | `/job-query` | ✅ 已完成 |
| 批次追蹤工具 | `/query-tool` | ✅ 已完成 |
| 生產歷史分析 | `/production-history` | ✅ 已完成 |

### 管理與基礎設施

| 功能 | 狀態 |
|------|------|
| Portal Shell no-iframe SPA 路由 | ✅ 已完成 |
| Portal 動態抽屜導覽管理 | ✅ 已完成 |
| 管理員認證系統（LDAP） | ✅ 已完成 |
| 統一管理儀表板（`/admin-dashboard`） | ✅ 已完成 |
| 效能監控儀表板（`/admin/performance`） | ✅ 已完成 |
| 使用者用量 KPI 儀表板（`/admin-user-usage-kpi`） | ✅ 已完成 |
| AI 智能查詢助手（Text2SQL / Function / Agent 模式） | ✅ 已完成 |
| 異常偵測排程器（DuckDB 自動分析） | ✅ 已完成 |
| Redis 多層快取系統 | ✅ 已完成 |
| DuckDB 快取查詢引擎（後端 + 前端 WASM） | ✅ 已完成 |
| RQ 非同步任務佇列（trace/reject/production-history/yield-alert/msd worker） | ✅ 已完成 |
| 熔斷器保護機制 | ✅ 已完成 |
| Worker 記憶體防護（RSS guard + OOM 保護） | ✅ 已完成 |
| Worker Watchdog 重啟控制 | ✅ 已完成 |
| Runtime 韌性診斷（threshold/churn/recommendation） | ✅ 已完成 |
| SQL 查詢安全架構 + 白名單防注入 | ✅ 已完成 |
| 全域安全標頭（CSP/XFO/HSTS） | ✅ 已完成 |
| CSRF 防護（admin form/mutation API） | ✅ 已完成 |
| 前端核心模組測試（Node test） | ✅ 已完成 |
| CSS 治理自動檢查 | ✅ 已完成 |
| 部署自動化 + systemd 服務 | ✅ 已完成 |

---

## 技術架構

### 後端技術棧

| 技術 | 版本 | 用途 |
|------|------|------|
| Python | 3.11+ | 程式語言 |
| Flask | 3.x | Web 框架 |
| Gunicorn | 21.x+ | WSGI 伺服器 |
| SQLAlchemy | 2.x | ORM / 連線池 |
| oracledb | 2.x+ | Oracle 驅動 |
| Redis | 7.x | 快取伺服器 |
| Pandas | 2.3 | 資料處理 |
| PyArrow | 17.x+ | Parquet 序列化（Redis DataFrame 快取） |
| DuckDB | 1.x | 快取查詢引擎（Parquet 支援的 reject/yield SQL runtime） |
| RQ | 1.16+ | 非同步任務佇列（trace/reject/production-history/yield-alert/msd） |
| Requests + PyYAML | — | LLM API 呼叫 + AI function registry |

### 前端技術棧

| 技術 | 版本 | 用途 |
|------|------|------|
| Vue 3 | 3.5 | UI 框架（所有報表頁面已遷移） |
| Vue Router | 4.6 | Portal Shell SPA 路由 |
| Vite | 6.3 | 多頁模組打包（19 個 entry point） |
| ECharts | 6.0 | 圖表庫（npm tree-shaking） |
| vue-echarts | 8.0 | ECharts Vue 封裝 |
| DuckDB-WASM | 1.33+ | 瀏覽器端本地運算（view compute offload） |
| Tailwind CSS | 3.4 | 樣式框架 |

### 資料庫

- Oracle Database 19c Enterprise Edition
- 主機與服務名：詳見 `.env` 檔案（`DB_HOST`、`DB_PORT`、`DB_SERVICE`）

---

## 專案結構

```
DashBoard_vite/
├── src/mes_dashboard/              # 後端主程式
│   ├── app.py                      # Flask 應用工廠
│   ├── config/                     # 設定
│   │   ├── settings.py             # 環境設定
│   │   ├── constants.py            # 常數定義
│   │   ├── tables.py               # 資料表 schema
│   │   ├── field_contracts.py      # UI/API/Export 欄位契約
│   │   └── workcenter_groups.py    # 工作中心群組設定
│   ├── core/                       # 核心模組（28 個）
│   │   ├── database.py             # Oracle 連線池
│   │   ├── redis_client.py         # Redis 客戶端
│   │   ├── redis_df_store.py       # Parquet DataFrame 序列化
│   │   ├── cache.py / cache_updater.py  # 快取管理 + 自動更新
│   │   ├── circuit_breaker.py      # 熔斷器
│   │   ├── rate_limit.py           # API 頻率限制
│   │   ├── resilience.py           # 韌性診斷
│   │   ├── response.py             # 統一 API 回應格式
│   │   ├── csrf.py                 # CSRF 防護
│   │   ├── permissions.py          # 權限管理
│   │   ├── worker_memory_guard.py  # Worker RSS 記憶體防護
│   │   ├── query_spool_store.py    # 查詢結果暫存（磁碟 spool）
│   │   ├── feature_flags.py        # Feature flag 引擎
│   │   ├── metrics.py / metrics_history.py  # 效能指標
│   │   ├── runtime_contract.py     # Runtime 啟動校驗
│   │   ├── worker_recovery_policy.py  # Worker 重啟策略
│   │   └── ...                     # 其他基礎設施
│   ├── routes/                     # 路由層（20 個 Blueprint）
│   │   ├── wip_routes.py           # WIP API
│   │   ├── resource_routes.py      # 設備即時 API
│   │   ├── resource_history_routes.py  # 設備歷史 API
│   │   ├── hold_routes.py / hold_overview_routes.py / hold_history_routes.py
│   │   ├── reject_history_routes.py  # 不良歷史 API
│   │   ├── yield_alert_routes.py   # 良率警示 API
│   │   ├── material_trace_routes.py  # 材料追溯 API
│   │   ├── mid_section_defect_routes.py  # 中段不良 API
│   │   ├── qc_gate_routes.py       # QC-GATE API
│   │   ├── query_tool_routes.py / job_query_routes.py
│   │   ├── spool_routes.py         # 查詢結果 spool API
│   │   ├── trace_routes.py         # 追溯非同步任務 API
│   │   ├── admin_routes.py / auth_routes.py / health_routes.py
│   │   └── dashboard_routes.py     # 儀表板 API
│   ├── services/                   # 服務層（45+ 模組）
│   │   ├── wip_service.py          # WIP 業務邏輯
│   │   ├── resource_service.py / resource_cache.py / resource_dataset_cache.py
│   │   ├── resource_history_service.py / resource_history_sql_runtime.py
│   │   ├── hold_dataset_cache.py / hold_history_service.py / hold_history_sql_runtime.py
│   │   ├── reject_dataset_cache.py / reject_history_service.py / reject_cache_sql_runtime.py
│   │   ├── reject_pareto_materialized.py  # Pareto 物化彙總層
│   │   ├── reject_query_job_service.py    # RQ reject 查詢任務
│   │   ├── yield_alert_service.py / yield_alert_dataset_cache.py / yield_alert_sql_runtime.py
│   │   ├── material_trace_service.py / lineage_engine.py  # 材料追溯 + BFS 族譜引擎
│   │   ├── mid_section_defect_service.py  # 中段不良三段管線
│   │   ├── batch_query_engine.py   # 批次查詢引擎（Redis+Parquet 快取）
│   │   ├── event_fetcher.py        # 非同步事件收集
│   │   ├── async_query_job_service.py / trace_job_service.py  # RQ 任務管理
│   │   ├── ai_query_service.py / ai_agent_loop.py  # AI 智能查詢（Text2SQL/Function/Agent）
│   │   ├── anomaly_detection_scheduler.py  # 異常偵測排程
│   │   ├── filter_cache.py         # 篩選選項快取
│   │   ├── realtime_equipment_cache.py  # 即時設備狀態快取
│   │   ├── page_registry.py / navigation_contract.py  # 頁面/導覽管理
│   │   └── container_resolution_policy.py  # LOT/WAFER 解析策略
│   ├── sql/                        # SQL 查詢模板（85+ 檔案）
│   │   ├── loader.py / builder.py / filters.py  # SQL 基礎設施
│   │   ├── dashboard/              # 儀表板 KPI
│   │   ├── wip/                    # WIP 查詢
│   │   ├── resource/ / resource_history/  # 設備查詢
│   │   ├── hold_history/           # Hold 歷史
│   │   ├── reject_history/         # 不良歷史（14 檔案）
│   │   ├── yield_alert/            # 良率警示
│   │   ├── query_tool/             # 通用查詢（22 檔案）
│   │   ├── mid_section_defect/     # 中段不良追溯
│   │   ├── lineage/                # LOT 族譜
│   │   ├── material_trace/         # 材料追溯
│   │   └── job_query/              # 設備維修
│   └── templates/                  # HTML 模板（admin 頁面）
├── frontend/                       # Vite 前端專案
│   ├── src/
│   │   ├── core/                   # 共用模組
│   │   │   ├── api.js              # REST API 客戶端
│   │   │   ├── duckdb-client.js    # DuckDB-WASM 客戶端
│   │   │   ├── duckdb-activation-policy.js  # 本地運算啟用策略
│   │   │   ├── autocomplete.js     # WIP autocomplete
│   │   │   ├── wip-derive.js       # WIP KPI/filter/chart 導出
│   │   │   ├── field-contracts.js  # 欄位契約
│   │   │   ├── shell-navigation.js # 導覽結構
│   │   │   └── ...                 # 其他 helpers
│   │   ├── shared-ui/              # 全站共用 UI 元件（AiChatPanel/DataTable/LoadingOverlay 等）
│   │   ├── shared-composables/     # 共用 Vue composables
│   │   ├── styles/                 # 全站 Tailwind CSS
│   │   ├── portal-shell/           # Portal Shell SPA（主路由容器）
│   │   ├── wip-overview/           # WIP 即時概況（Vue 3 SFC）
│   │   ├── wip-detail/             # WIP 明細查詢（Vue 3 SFC）
│   │   ├── wip-shared/             # WIP 共用 CSS/常數/元件
│   │   ├── hold-detail/            # Hold 明細分析（Vue 3 SFC）
│   │   ├── hold-overview/          # Hold 即時概況（Vue 3 SFC）
│   │   ├── hold-history/           # Hold 歷史績效（Vue 3 SFC）
│   │   ├── resource-status/        # 設備即時概況（Vue 3 SFC）
│   │   ├── resource-history/       # 設備歷史績效（Vue 3 SFC）
│   │   ├── resource-shared/        # 設備共用 CSS/常數/HierarchyTable
│   │   ├── qc-gate/                # QC-GATE 即時狀態（Vue 3 SFC）
│   │   ├── reject-history/         # 不良歷史分析（Vue 3 SFC）
│   │   ├── yield-alert-center/     # 良率警示中心（Vue 3 SFC）
│   │   ├── mid-section-defect/     # 中段不良追溯（Vue 3 SFC）
│   │   ├── material-trace/         # 材料追溯（Vue 3 SFC）
│   │   ├── tables/                 # 數據表查詢（Vue 3 SFC）
│   │   ├── production-history/      # 生產歷史分析（Vue 3 SFC）
│   │   ├── admin-dashboard/        # 統一管理儀表板（Vue 3 SFC）
│   │   ├── admin-performance/      # 效能監控（Vue 3 SFC）
│   │   ├── admin-user-usage-kpi/   # 使用者用量 KPI（Vue 3 SFC）
│   │   ├── job-query/              # 設備維修查詢
│   │   ├── query-tool/             # 批次追蹤工具
│   │   ├── workers/                # Web Worker（DuckDB 等）
│   │   └── portal/                 # Portal 入口
│   ├── tests/                      # 前端測試（Node test runner）
│   ├── vite.config.js              # 19 個 entry point 打包設定
│   ├── tailwind.config.js          # 設計 token（色彩/間距/字型）
│   └── package.json
├── shared/
│   └── field_contracts.json        # 前後端共用欄位契約
├── contract/                       # 開發契約
│   ├── api_development_contract.md # API 開發規範
│   ├── api_inventory.md            # API 端點清冊
│   ├── css_development_contract.md # CSS 開發規範
│   └── css_inventory.md            # CSS 來源清冊
├── scripts/                        # 腳本
│   ├── deploy.sh                   # 自動部署腳本
│   ├── start_server.sh             # 服務生命週期管理
│   ├── worker_watchdog.py          # Worker 健康監控
│   ├── run_cache_benchmarks.py     # 快取效能基準
│   ├── sql_optimization_verify.py  # SQL 優化驗證
│   └── run_stress_tests.py         # 壓力測試
├── deploy/                         # systemd 服務設定
│   ├── mes-dashboard.service       # Gunicorn 服務
│   ├── mes-dashboard-trace-worker.service   # RQ trace worker 服務
│   ├── mes-dashboard-reject-worker.service  # RQ reject worker 服務
│   ├── mes-dashboard-msd-worker.service     # RQ MSD lineage worker 服務
│   └── mes-dashboard-watchdog.service       # Watchdog 服務
├── tests/                          # 後端測試（pytest，127+ 檔案）
├── docs/                           # 技術文件
├── openspec/                       # 變更規格管理
├── tools/                          # 資料庫/文件工具
├── data/                           # 執行期資料
├── logs/                           # 應用日誌
├── .env.example                    # 環境變數範例
├── requirements.txt                # Python 依賴
├── environment.yml                 # Conda 環境定義
├── gunicorn.conf.py                # Gunicorn 設定
└── pytest.ini                      # pytest 設定
```

---

## 架構重點

### 1. Portal Shell — no-iframe SPA 路由

- Shell 內容切換全面使用 Vue Router + native route-view，不使用 iframe
- 動態抽屜導覽、fallback routing、admin 可見性規則由 `/api/portal/navigation` + route contract 驅動
- shell 健康狀態採 summary-first，詳細診斷由互動展開（`/health/frontend-shell`）

### 2. 單一 Port 架構

- Flask + Gunicorn + Vite dist 由同一服務提供（`GUNICORN_BIND`），前後端同源
- Vite 建置輸出至 `static/dist/`，由 Flask 提供靜態檔案

### 3. 多層快取策略

- **Process-level cache**：bounded LRU（WIP/Resource/Equipment），TTL 30s
- **Redis cache**：DataFrame Parquet 序列化、篩選選項、分析結果
- **DuckDB SQL runtime**（後端）：Parquet 檔案上的 SQL 查詢（reject-history、yield-alert）
- **DuckDB-WASM**（前端）：瀏覽器端 view compute offload（resource-history、hold-history）
- **Query spool store**：大型查詢結果暫存到磁碟，避免記憶體峰值

### 4. 非同步任務處理

- **RQ task queue**：五個專用 worker 佇列（trace-events、reject-query、production-history、yield-alert、msd-lineage）
- **Event Fetcher**：批次容錯收集（可設定 partial failure 策略）+ streaming spool（無 row 上限）
- **Batch Query Engine**：長時間查詢拆批 + Redis+Parquet 快取

### 5. Runtime 韌性

- `/health`、`/health/deep`、`/admin/api/system-status` 提供門檻、policy state、restart churn 摘要與 recovery recommendation
- Circuit Breaker（CLOSED → OPEN → HALF_OPEN）保護資料庫免於雪崩
- Worker Watchdog：cooldown + retry budget + churn window；超標進入 guarded mode 需 admin override
- **Worker 記憶體防護**：RSS projection + graduated response（warn → restrict → force-recycle）

### 6. AI 智能查詢

- **三種運作模式**：Text2SQL（自然語言 → SQL）、Function（工具呼叫 + function registry）、Agent（迭代式精煉）
- **Schema 感知**：AI Schema Context 自動內省表格/欄位 + 相關性篩選
- **業務語境**：AI Business Context 提供領域詞彙、範例查詢
- **三輪澄清**：AI Query Understanding 意圖分類 + 追問管線
- **前端整合**：`AiChatPanel` 共用元件，嵌入各報表頁面
- **LLM 端點**：可配置 Ollama 或相容 API（`AI_API_URL`、`AI_MODEL`）
- **頻率控制**：預設 3 請求/60 秒

### 7. 異常偵測

- **排程 daemon**：每日自動執行（可配置時段，預設 08:00）
- **DuckDB 運算**：獨立命名空間（`anomaly_*_dataset`）避免與使用者查詢衝突
- **Pre-seed**：排程器預產 spool Parquet 檔案，結果快取至 Redis 供所有 worker 共享

### 8. 安全防護

- Production `SECRET_KEY` 缺失時啟動失敗（fail-fast）
- CSRF token 驗證（admin form + admin mutation API）
- LDAP API URL 啟動驗證（`https` + host allowlist）
- 全域 security headers（CSP/X-Frame-Options/X-Content-Type-Options/Referrer-Policy/HSTS）
- Table Query API `table_name` 白名單驗證
- SQL 參數化查詢 + LIKE 萬用字元跳脫
- 高成本 API 頻率限制（in-process rate limit）
- 共用解析防護（LOT/WAFER 輸入筆數上限、萬用字元前最少字首長度）

---

## 快速開始

### 首次部署

```bash
# 1. 執行部署腳本（自動建立 Conda 環境、安裝依賴、驗證連線）
./scripts/deploy.sh

# 2. 編輯環境設定
nano .env

# 3. 建置前端
npm --prefix frontend install
npm --prefix frontend run build

# 4. 啟動服務
./scripts/start_server.sh start
```

### 日常操作

```bash
# 啟動服務（背景執行，含 Gunicorn + Redis + RQ workers + Watchdog）
./scripts/start_server.sh start

# 停止服務
./scripts/start_server.sh stop

# 重啟服務
./scripts/start_server.sh restart

# 查看狀態
./scripts/start_server.sh status

# 查看日誌
./scripts/start_server.sh logs follow
./scripts/start_server.sh logs watchdog
```

訪問網址：**http://localhost:8080**（可在 `.env` 中配置 `GUNICORN_BIND`）

---

## 部署指南

### 環境需求

- Python 3.11+
- Conda（Miniconda / Anaconda）
- Node.js 22+（建議由 Conda `environment.yml` 管理）
- Oracle Database 連線
- Redis Server 7.x+

### 自動部署（推薦）

```bash
./scripts/deploy.sh
```

此腳本會自動：檢查 Conda 環境 → 建立 `mes-dashboard` 虛擬環境 → 安裝依賴套件 → 複製 `.env.example` → 驗證資料庫連線。

### 手動部署

```bash
# 建立 Conda 環境
conda create -n mes-dashboard python=3.11 -y
conda activate mes-dashboard

# 安裝後端依賴
pip install -r requirements.txt

# 安裝前端依賴並建置
npm --prefix frontend install
npm --prefix frontend test
npm --prefix frontend run build

# 設定環境變數
cp .env.example .env
nano .env

# 啟動服務
./scripts/start_server.sh start
```

### 環境變數設定

編輯 `.env` 檔案（完整範例見 `.env.example`）。主要類別：

| 類別 | 關鍵變數 | 說明 |
|------|----------|------|
| 資料庫 | `DB_HOST`, `DB_PORT`, `DB_SERVICE`, `DB_USER`, `DB_PASSWORD` | Oracle 連線（必填） |
| Flask | `FLASK_ENV`, `SECRET_KEY` | 生產環境必須設定 `SECRET_KEY` |
| Gunicorn | `GUNICORN_BIND`, `GUNICORN_WORKERS`, `GUNICORN_THREADS` | 服務監聽與 worker 設定 |
| Redis | `REDIS_URL`, `REDIS_ENABLED`, `REDIS_MAXMEMORY` | 快取伺服器設定 |
| DB 韌性 | `DB_POOL_SIZE`, `DB_CALL_TIMEOUT_MS`, `CIRCUIT_BREAKER_*` | 連線池與熔斷器 |
| 安全 | `CSRF_ENABLED`, `LDAP_API_URL`, `LDAP_ALLOWED_HOSTS`, `ADMIN_EMAILS` | 認證與授權 |
| Worker 策略 | `WORKER_RESTART_*`, `RESILIENCE_*` | Watchdog 重啟與韌性門檻 |
| Rate Limit | `WIP_MATRIX_RATE_LIMIT_*`, `RESOURCE_*_RATE_LIMIT_*` | 高成本 API 頻率限制 |
| 記憶體防護 | `PROCESS_CACHE_MAX_SIZE`, `WIP_PROCESS_CACHE_MAX_SIZE` | Process-level LRU 快取 |
| AI 查詢 | `AI_API_URL`, `AI_MODEL`, `AI_MODE`, `AI_REQUEST_TIMEOUT` | LLM 端點與模式設定 |
| 異常偵測 | `ANOMALY_DETECTION_HOUR` | 排程執行時段（預設 08:00） |

### 生產環境注意事項

1. **SECRET_KEY**：必須設定為隨機字串
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
2. **FLASK_ENV**：設定為 `production`
3. **防火牆**：開放服務端口（預設 8080）

### Conda + systemd 服務配置

```bash
# 1. 複製 systemd 服務檔案
sudo cp deploy/mes-dashboard.service /etc/systemd/system/
sudo cp deploy/mes-dashboard-trace-worker.service /etc/systemd/system/
sudo cp deploy/mes-dashboard-reject-worker.service /etc/systemd/system/
sudo cp deploy/mes-dashboard-watchdog.service /etc/systemd/system/

# 2. 確認 .env 權限
sudo chown root:www-data /opt/mes-dashboard/.env
sudo chmod 640 /opt/mes-dashboard/.env

# 3. 啟用服務
sudo systemctl daemon-reload
sudo systemctl enable --now mes-dashboard mes-dashboard-trace-worker mes-dashboard-reject-worker mes-dashboard-msd-worker mes-dashboard-watchdog

# 4. 驗證 runtime contract
RUNTIME_CONTRACT_ENFORCE=true ./scripts/start_server.sh check
```

### Rollback 步驟

```bash
./scripts/start_server.sh stop
sudo systemctl stop mes-dashboard mes-dashboard-trace-worker mes-dashboard-reject-worker mes-dashboard-msd-worker mes-dashboard-watchdog
git checkout <previous-commit>
pip install -r requirements.txt
npm --prefix frontend install && npm --prefix frontend run build
./scripts/start_server.sh start
sudo systemctl start mes-dashboard mes-dashboard-trace-worker mes-dashboard-reject-worker mes-dashboard-msd-worker mes-dashboard-watchdog
```

---

## 功能說明

### Portal 入口頁面

透過側邊欄抽屜分組導覽切換各功能模組：
- **即時報表**：WIP 即時概況、設備即時概況、QC-GATE 狀態
- **歷史報表**：設備歷史績效、Hold 歷史績效、不良歷史分析、良率警示中心
- **查詢工具**：設備維修查詢、Excel 查詢工具、批次追蹤工具、材料追溯
- **分析工具**：生產歷史分析
- **開發工具**（admin only）：TMTT 不良分析、數據表查詢、頁面管理、效能監控、使用者用量 KPI
- 抽屜/頁面配置可由管理員動態管理（新增、重排、刪除）

### WIP 即時概況

- 總覽統計卡片（Total Lots/QTY + RUN/QUEUE/品質異常/非品質異常）
- Workcenter × Package 矩陣表（Top 15 欄、sticky 首欄、Total 行列）
- Hold Pareto 分析（ECharts 雙軸柏拉圖 + 明細表）
- Autocomplete 篩選（WORKORDER/LOT/PACKAGE/TYPE，cross-filter + 300ms debounce）
- 矩陣點擊 drill-down 至 WIP Detail、Pareto drill-down 至 Hold Detail；返回保留篩選條件
- 10 分鐘自動刷新 + AbortController 請求取消

### WIP 明細查詢

- 依工作中心顯示 LOT 明細（4 sticky 欄 + 動態 Spec 欄位）
- 狀態卡片篩選 + Autocomplete cross-filter + 伺服器端分頁
- 點擊 LOT ID 展開 inline 詳細面板（基本/產品/製程/物料/Hold/NCR）
- URL params 接收 Overview drill-down 參數

### Hold 明細 / 即時概況 / 歷史績效

- **Hold Detail**：依 Hold 原因摘要統計、Age 分布卡片篩選、LOT 明細分頁
- **Hold Overview**：Summary cards + Workcenter×Package Matrix（QTY）+ Lot 明細分頁；多選 Reason 篩選
- **Hold History**：Daily Trend + Record type 篩選 + Reason Pareto + Duration 分布 + 明細分頁

### 設備即時概況

- 10 張 KPI 卡片（OU%/AVAIL%/PRD/SBY/UDT/SDT/EGT/NST/OTHER/Total）
- 三層階層矩陣表（workcenter group → family → resource），支援展開/收合與 cell click 篩選
- 設備卡片格 + LOT/JOB 浮動 tooltip（`<Teleport>` + viewport clamp）
- Group/Family/Machine 級聯篩選 + 生產設備/重點設備/監控設備 checkbox
- 5 分鐘自動刷新 + `visibilitychange` 即時刷新 + Cache 狀態指示

### 設備歷史績效

- OEE KPI 整合（稼動率 × 效能率 × 良率）+ 9 張 KPI 卡片
- 4 個 vue-echarts 圖表（趨勢折線/堆疊柱狀/workcenter 對比/OU% 熱圖）
- 三層階層明細表（`HierarchyTable`），hours + percentage 格式
- 日期區間 + 粒度切換（日/週/月/年）+ Group/Family/Machine 級聯多選
- DuckDB-WASM 前端 view compute offload + CSV 串流匯出

### QC-GATE 即時狀態報表

- QC-GATE 站點 LOT 即時分佈堆疊條圖（等待時間四級分類：<6hr/6-12hr/12-24hr/>24hr）
- 點擊條圖篩選 LOT 明細表；站點依製程順序排序
- 10 分鐘自動刷新，與 WIP 快取同步

### 不良歷史分析（Reject History）

- 多維度 Pareto 分析（3×2 grid：站點/不良原因/產品/封裝/機台/日期）
- 跨 Pareto 交叉篩選聯動 + 多選篩選
- DuckDB SQL runtime（Parquet 快取查詢）+ 物化 Pareto 彙總層
- 大量資料 backpressure + streaming spool merge
- RQ 非同步查詢 worker + partial failure 前端通知

### 良率警示中心（Yield Alert Center）

- 兩階段 dataset cache（summary + detail）
- 站點摘要 + 熱圖 + 粒度切換（日/週/月）
- 產品/封裝欄位 + 展開原因明細
- DuckDB out-of-core view computation + 記憶體防護

### 材料追溯查詢（Material Trace）

- 雙向 LOT/材料追溯（正向 forward + 反向 reverse）
- 非同步多階段查詢（trace-events RQ worker）+ 進度條
- 族譜引擎（BFS 分批鏈 + 合批展開）

### 中段製程不良追溯分析

- TMTT 測試站不良回溯至上游機台/站點/製程
- 三段式資料管線：TMTT 偵測 → LOT 族譜解析 → 上游製程歷史
- 6 張 KPI 卡片 + 6 張 Pareto 圖表 + 日趨勢 + LOT 明細分頁
- 不良原因多選篩選（205 種，24h Redis 快取）

### 生產歷史分析（Production History）

- 歷史生產量矩陣（Workcenter × 日期）+ 明細表
- 日期區間篩選 + RQ 非同步查詢（production-history worker）
- DuckDB SQL runtime 處理大量歷史數據

### 數據表查詢工具

- DWH 表格分類卡片目錄（即時/快照/歷史/輔助）+ 大表標記
- 選擇表格後自動載入欄位、支援每欄篩選 + tag 管理
- 白名單驗證防止 SQL injection

### 管理員功能

- LDAP 認證登入（支援本地測試模式）
- 頁面狀態管理（released/dev）+ 抽屜管理（CRUD + 排序）
- 統一管理儀表板（`/admin-dashboard`）：
  - Overview：系統狀態總覽（Database/Redis/Circuit Breaker/Worker）
  - Cache：快取命中率、TTL、記憶體用量
  - Logs：系統日誌檢視 + 日誌管理
  - Worker：Worker 狀態控制 + RSS 記憶體監控
  - Performance：查詢效能指標（P50/P95/P99 延遲/慢查詢統計）
  - Usage：使用者登入/用量 KPI
- 使用者用量 KPI 儀表板（`/admin-user-usage-kpi`）：
  - DAU 趨勢、時段分布、部門統計、Top 使用者排行

---

## 測試

```bash
# 執行所有後端測試
pytest tests/ -v

# 執行前端測試
npm --prefix frontend test

# 執行 CSS 治理檢查
npm --prefix frontend run css:check

# Cache benchmark gate
conda run -n mes-dashboard python scripts/run_cache_benchmarks.py --enforce

# SQL 優化驗證
conda run -n mes-dashboard python scripts/sql_optimization_verify.py

# 壓力測試
pytest tests/stress/ -v
```

---

## 開發契約

本專案執行嚴格的開發契約治理，詳見 `/contract` 目錄：

- **API 開發契約**（`contract/api_development_contract.md`）：統一回應格式、Route/Service 分離、API 清冊同步
- **CSS 開發契約**（`contract/css_development_contract.md`）：Tailwind-first、Feature 樣式隔離、CSS 清冊同步
- **欄位契約**（`shared/field_contracts.json`）：前後端共用的 UI/API/Export 欄位定義

---

## 相關文件

| 文件 | 說明 |
|------|------|
| `docs/MES_Database_Reference.md` | MES 資料庫表格參考 |
| `docs/Oracle_Authorized_Objects.md` | Oracle 存取權限規格 |
| `docs/hold_history.md` | Hold 歷史頁資料口徑說明 |
| `docs/migration_gates_and_runbook.md` | 遷移門檻與 Rollback Runbook |
| `docs/environment_gaps_and_mitigation.md` | 環境依賴缺口與對策 |
| `CLAUDE.md` | AI 輔助開發規範 |

---

## 故障排除

### 服務無法啟動

1. 確認 Conda 環境：`conda activate mes-dashboard`
2. 確認依賴：`pip install -r requirements.txt`
3. 確認 runtime contract：`RUNTIME_CONTRACT_ENFORCE=true ./scripts/start_server.sh check`
4. 查看日誌：`./scripts/start_server.sh logs error`

### 資料庫連線失敗

1. 確認 `.env` 中的 `DB_HOST`/`DB_PORT`/`DB_SERVICE`/`DB_USER`/`DB_PASSWORD`
2. 確認網路連線 + 帳號密碼
3. 檢查 circuit breaker 狀態：`/health/deep`

### Port 被占用

```bash
lsof -i :8080
# 修改 .env 中的 GUNICORN_BIND
```

### Worker OOM

1. 檢查 `/admin/performance` 的 RSS 記憶體面板
2. 調整 `PROCESS_CACHE_MAX_SIZE` 降低快取記憶體
3. Worker memory guard 會自動 graduated response（warn → restrict → force-recycle）

---

## 聯絡方式

如有技術問題或需求變更，請聯繫系統管理員。

---

**文檔版本**: 7.0
**最後更新**: 2026-04-01
