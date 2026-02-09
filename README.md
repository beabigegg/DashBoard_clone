# MES Dashboard 報表系統

基於 Flask + Gunicorn + Redis + Vite 的 MES 數據報表查詢與可視化系統

> 專案主執行根目錄：`DashBoard_vite/`  
> 目前已移除舊版 `DashBoard/` 代碼，僅保留新架構。

---

## 專案狀態

| 功能 | 狀態 |
|------|------|
| WIP 即時概況 | ✅ 已完成 |
| WIP 明細查詢 | ✅ 已完成 |
| Hold 狀態分析 | ✅ 已完成 |
| 數據表查詢工具 | ✅ 已完成 |
| 設備狀態監控 | ✅ 已完成 |
| 設備歷史查詢 | ✅ 已完成 |
| 管理員認證系統 | ✅ 已完成 |
| 頁面狀態管理 | ✅ 已完成 |
| Redis 快取系統 | ✅ 已完成 |
| SQL 查詢安全架構 | ✅ 已完成 |
| 效能監控儀表板 | ✅ 已完成 |
| 熔斷器保護機制 | ✅ 已完成 |
| Worker 重啟控制 | ✅ 已完成 |
| Runtime 韌性診斷（threshold/churn/recommendation） | ✅ 已完成 |
| WIP 共用 autocomplete core 模組 | ✅ 已完成 |
| WIP 共用 derive core 模組（KPI/filter/chart/table） | ✅ 已完成 |
| WIP 索引查詢加速與增量同步 | ✅ 已完成 |
| 快取記憶體放大係數 telemetry | ✅ 已完成 |
| Cache benchmark gate（P95/記憶體門檻） | ✅ 已完成 |
| Worker guarded mode + manual override 稽核 | ✅ 已完成 |
| Runtime contract 啟動校驗（conda/systemd/watchdog） | ✅ 已完成 |
| 前端核心模組測試（Node test） | ✅ 已完成 |
| 部署自動化 | ✅ 已完成 |
| Portal 動態抽屜導覽管理 | ✅ 已完成 |
| QC-GATE 即時狀態報表（Vue 3 + Vite） | ✅ 已完成 |
| 數據表查詢頁面 Vue 3 遷移 | ✅ 已完成 |
| WIP 三頁 Vue 3 遷移（Overview/Detail/Hold Detail） | ✅ 已完成 |
| 設備快取 DataFrame TTL 一致性修復 | ✅ 已完成 |

---

## 開發歷史（Vite 重構後）

- 2026-02-09：完成 WIP 三頁 Vue 3 遷移（`/wip-overview`、`/wip-detail`、`/hold-detail`）— 三頁共 1,941 行 vanilla JS + Jinja2 重寫為 Vue 3 SFC。抽取共用 CSS/常數/元件至 `wip-shared/`，Pareto 圖改用 vue-echarts（與 QC-GATE 一致），Hold Detail 新增前端 URL params 判斷取代 Jinja2 注入。
- 2026-02-09：完成數據表查詢頁面（`/tables`）Vue 3 遷移 — 第二個純 Vite 頁面，建立 `apiPost` POST 請求模式，237 行 vanilla JS 重寫為 Vue 3 SFC 元件。
- 2026-02-09：修復設備快取 DataFrame TTL 一致性問題 — process-level DataFrame（30s TTL）過期後 derived index 仍為 ready，導致 `/api/resource/status` 回傳空資料。新增 Redis fallback reload。
- 2026-02-09：新增 QC-GATE 即時狀態報表 — 第一個純 Vue 3 + Vite 頁面（脫離 Jinja2），建立後續前端遷移架構模式。
- 2026-02-09：完成 Portal 動態抽屜導覽管理，sidebar drawer/page 配置改為 admin 可管理。
- 2026-02-07：完成 Flask + Vite 單一 port 架構切換，舊版 `DashBoard/` 停用。
- 2026-02-08：補齊 runtime 韌性治理（threshold/churn/recommendation）與 watchdog 可觀測欄位。
- 2026-02-08：完成 P0 安全/穩定性硬化：
  - production `SECRET_KEY` 缺失時啟動失敗（fail-fast）
  - admin form + admin mutation API CSRF 防護
  - health probe 使用獨立 DB pool，避免與主查詢池互相阻塞
  - worker/app shutdown 統一清理 cache updater、realtime sync、Redis、DB engine
  - `hold_detail` inline script 變數改為 `tojson` 序列化
- 2026-02-08：完成 P1 快取/查詢效率重構：
  - WIP 查詢路徑改為索引選擇，保留 `resource/wip` 全表快取語意
  - WIP search index 增量同步（watermark/version）與 drift fallback
  - health/admin 新增 cache memory amplification telemetry
  - 建立 `scripts/run_cache_benchmarks.py` + fixture gate
- 2026-02-08：完成 P2 運維自癒治理：
  - runtime contract 共用化（app/start_server/watchdog/systemd）
  - 啟動時 conda/watchdog 路徑 drift fail-fast
  - worker restart policy（cooldown/retry budget/churn guarded mode）
  - manual override（需 ack + reason）與結構化 audit log
- 2026-02-08：完成 round-2 安全/穩定補強：
  - LDAP endpoint 改為嚴格驗證（`https` + `LDAP_ALLOWED_HOSTS`）
  - process-level cache 新增 `max_size + LRU`（WIP/Resource）
  - circuit breaker transition logging 移至鎖外，降低 lock contention
  - 全域安全標頭（CSP/XFO/nosniff/Referrer-Policy，production 加 HSTS）
  - WIP detail 分頁參數加上下限（`page>=1`、`1<=page_size<=500`）
- 2026-02-08：完成 round-3 殘餘風險修補：
  - WIP cache publish 採 staged publish，失敗不污染舊快照
  - WIP slow-path parse 移至鎖外；realtime equipment process cache 補齊 bounded LRU
  - resource NaN 清理改為 depth-safe 迭代；WIP/Hold 布林查詢解析共用化
  - filter cache view 名稱改為 env 可配置
  - `/health`、`/health/deep` 新增 5 秒內部 memo（testing 模式禁用）
  - 高成本 API 增加輕量 rate limit（WIP detail/matrix、Hold lots、Resource status/detail）
  - DB 連線字串 log redaction 遮罩密碼
- 2026-02-08：完成 round-4 殘餘治理收斂：
  - Resource derived index 改為 row-position representation，移除 process 內 full records 複本
  - Resource / Realtime Equipment 共用 Oracle SQL fragments，降低查詢定義漂移
  - `resource_cache` / `realtime_equipment_cache` 型別註記與高頻常數命名收斂
  - `page_registry` 寫檔改為 atomic replace（tmp + rename），避免設定檔半寫入
  - 新增測試保護：共享 SQL 片段、index normalization、route bool parser 不重複定義

---

## 遷移與驗收文件

- Root cutover 盤點：`docs/root_cutover_inventory.md`
- 頁面架構與抽屜分類：`docs/page_architecture_map.md`
- 前端計算前移與 parity 規則：`docs/frontend_compute_shift_plan.md`
- Cutover gates / rollout / rollback：`docs/migration_gates_and_runbook.md`
- 環境依賴缺口與對策：`docs/environment_gaps_and_mitigation.md`

---

## 最新架構重點

1. 單一 port 契約維持不變
- Flask + Gunicorn + Vite dist 由同一服務提供（`GUNICORN_BIND`），前後端同源。

2. Runtime 韌性採「降級 + 可操作建議 + policy state」
- `/health`、`/health/deep`、`/admin/api/system-status`、`/admin/api/worker/status` 皆提供：
  - 門檻（thresholds）
  - policy state（`allowed` / `cooldown` / `blocked`）
  - 重啟 churn 摘要
  - alerts（pool/circuit/churn）
  - recovery recommendation（值班建議動作）

3. Watchdog 自癒策略具界限保護
- restart 流程納入 cooldown + retry budget + churn window。
- churn 超標時進入 guarded mode，需 admin manual override 才可繼續重啟。
- state 檔保留 bounded restart history，供 policy 與稽核使用。

4. 前端治理：WIP compute 共用化
- `frontend/src/core/autocomplete.js` 作為 WIP overview/detail 共用邏輯來源。
- `frontend/src/core/wip-derive.js` 共用 KPI/filter/chart/table 導出運算。
- 維持既有頁面流程與 drill-down 語意，不變更操作習慣。

5. P1 快取效率治理
- 保留 `resource`、`wip` 全表快取策略（業務約束不變）。
- 查詢改走索引選擇，並提供 memory amplification / index efficiency telemetry。
- 以 benchmark gate 驗證 P95 延遲與記憶體放大不超過門檻。

6. P0 Runtime Hardening（安全 + 穩定）
- Production 必須提供 `SECRET_KEY`；未設定時服務拒絕啟動。
- `/admin/login` 與 `/admin/api/*` 變更請求必須攜帶 CSRF token。
- `/health` 資料庫連通探針使用獨立 health pool，降低 pool 飽和時誤判。
- 關機/重啟時統一釋放 background workers 與 Redis/DB 連線資源。
- LDAP API URL 啟動驗證：僅允許 `https` + host allowlist。
- 全域 security headers：CSP/X-Frame-Options/X-Content-Type-Options/Referrer-Policy（production 含 HSTS）。

---

## 快速開始

### 首次部署

```bash
# 1. 執行部署腳本
./scripts/deploy.sh

# 2. 編輯環境設定
nano .env

# 3. 啟動服務
./scripts/start_server.sh start
```

### 日常操作

```bash
# 啟動服務（背景執行，含 Gunicorn + worker_watchdog）
./scripts/start_server.sh start

# 停止服務
./scripts/start_server.sh stop

# 重啟服務
./scripts/start_server.sh restart

# 查看狀態
./scripts/start_server.sh status

# 查看日誌（含 watchdog）
./scripts/start_server.sh logs follow
./scripts/start_server.sh logs watchdog
```

訪問網址: **http://localhost:8080** （可在 .env 中配置）

---

## 部署指南

### 環境需求

- Python 3.11+
- Conda (Miniconda/Anaconda)
- Node.js 22+（建議由 Conda `environment.yml` 管理）
- Oracle Database 連線
- Redis Server 7.x+ （設備狀態快取）

### 部署步驟

#### 1. 自動部署（推薦）

```bash
./scripts/deploy.sh
```

此腳本會自動：
- 檢查 Conda 環境
- 建立 `mes-dashboard` 虛擬環境
- 安裝依賴套件
- 複製 `.env.example` 到 `.env`
- 驗證資料庫連線

#### 2. 手動部署

```bash
# 建立 Conda 環境
conda create -n mes-dashboard python=3.11 -y
conda activate mes-dashboard

# 安裝依賴
pip install -r requirements.txt

# 安裝前端依賴並建置（Vite）
npm --prefix frontend install
npm --prefix frontend test
npm --prefix frontend run build

# 設定環境變數
cp .env.example .env
nano .env  # 編輯資料庫連線等設定

# 啟動服務
./scripts/start_server.sh start
```

### 環境變數設定

編輯 `.env` 檔案：

```bash
# 資料庫設定（必填）
DB_HOST=your_database_host
DB_PORT=1521
DB_SERVICE=your_service_name
DB_USER=your_username
DB_PASSWORD=your_password

# Flask 設定
FLASK_ENV=production          # production | development
SECRET_KEY=your-secret-key    # 生產環境請更換

# Gunicorn 設定
GUNICORN_BIND=0.0.0.0:8080    # 服務監聽位址
GUNICORN_WORKERS=2             # Worker 數量
GUNICORN_THREADS=4             # 每個 Worker 的執行緒數

# DB 韌性設定
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=1800
DB_CALL_TIMEOUT_MS=55000
DB_POOL_EXHAUSTED_RETRY_AFTER_SECONDS=5

# Health probe 專用 DB pool（與主 request pool 隔離）
DB_HEALTH_POOL_SIZE=1
DB_HEALTH_MAX_OVERFLOW=0
DB_HEALTH_POOL_TIMEOUT=2

# Circuit Breaker
CIRCUIT_BREAKER_ENABLED=true
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_FAILURE_RATE=0.5
CIRCUIT_BREAKER_RECOVERY_TIMEOUT=30

# Redis 設定
REDIS_URL=redis://localhost:6379/0
REDIS_ENABLED=true

# Watchdog runtime contract
WATCHDOG_RUNTIME_DIR=./tmp
WATCHDOG_RESTART_FLAG=./tmp/mes_dashboard_restart.flag
WATCHDOG_PID_FILE=./tmp/gunicorn.pid
WATCHDOG_STATE_FILE=./tmp/mes_dashboard_restart_state.json
WATCHDOG_RESTART_HISTORY_MAX=50
CONDA_BIN=/opt/miniconda3/bin/conda
CONDA_ENV_NAME=mes-dashboard
RUNTIME_CONTRACT_VERSION=2026.02-p2
RUNTIME_CONTRACT_ENFORCE=true

# Worker self-healing policy
WORKER_RESTART_COOLDOWN=60
WORKER_RESTART_RETRY_BUDGET=3
WORKER_RESTART_WINDOW_SECONDS=600
WORKER_RESTART_CHURN_THRESHOLD=3
WORKER_GUARDED_MODE_ENABLED=true

# Runtime resilience thresholds
RESILIENCE_DEGRADED_ALERT_SECONDS=300
RESILIENCE_POOL_SATURATION_WARNING=0.90
RESILIENCE_POOL_SATURATION_CRITICAL=1.0
RESILIENCE_RESTART_CHURN_WINDOW_SECONDS=600
RESILIENCE_RESTART_CHURN_THRESHOLD=3

# 管理員設定
ADMIN_EMAILS=admin@example.com # 管理員郵件（逗號分隔）
LDAP_API_URL=https://ldap-api.example.com
LDAP_ALLOWED_HOSTS=ldap-api.example.com,ldap-api-dr.example.com

# CSRF 防護（admin form/admin mutation API）
CSRF_ENABLED=true

# Process-level cache bounded LRU（WIP/Resource）
PROCESS_CACHE_MAX_SIZE=32
WIP_PROCESS_CACHE_MAX_SIZE=32
RESOURCE_PROCESS_CACHE_MAX_SIZE=32
EQUIPMENT_PROCESS_CACHE_MAX_SIZE=32

# Filter cache source views (env-overridable)
FILTER_CACHE_WIP_VIEW=DWH.DW_MES_LOT_V
FILTER_CACHE_SPEC_WORKCENTER_VIEW=DWH.DW_MES_SPEC_WORKCENTER_V

# Health internal memoization
HEALTH_MEMO_TTL_SECONDS=5

# High-cost API rate limit (in-process)
WIP_MATRIX_RATE_LIMIT_MAX_REQUESTS=120
WIP_MATRIX_RATE_LIMIT_WINDOW_SECONDS=60
WIP_DETAIL_RATE_LIMIT_MAX_REQUESTS=90
WIP_DETAIL_RATE_LIMIT_WINDOW_SECONDS=60
HOLD_LOTS_RATE_LIMIT_MAX_REQUESTS=90
HOLD_LOTS_RATE_LIMIT_WINDOW_SECONDS=60
RESOURCE_DETAIL_RATE_LIMIT_MAX_REQUESTS=60
RESOURCE_DETAIL_RATE_LIMIT_WINDOW_SECONDS=60
RESOURCE_STATUS_RATE_LIMIT_MAX_REQUESTS=90
RESOURCE_STATUS_RATE_LIMIT_WINDOW_SECONDS=60
```

### 生產環境注意事項

1. **SECRET_KEY**: 必須設定為隨機字串
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

2. **FLASK_ENV**: 設定為 `production`

3. **防火牆**: 開放服務端口（預設 8080）

### Conda + systemd 服務配置

建議在生產環境使用同一份 `.env`（`/opt/mes-dashboard/.env`）啟動 App 與 Watchdog，與開發環境一致：

```bash
# 1. 複製 systemd 服務檔案
sudo cp deploy/mes-dashboard.service /etc/systemd/system/
sudo cp deploy/mes-dashboard-watchdog.service /etc/systemd/system/

# 2. 確認 /opt/mes-dashboard/.env 權限（供 www-data 讀取）
sudo chown root:www-data /opt/mes-dashboard/.env
sudo chmod 640 /opt/mes-dashboard/.env

# 3. 重新載入 systemd
sudo systemctl daemon-reload

# 4. 啟動並設定開機自動啟動
sudo systemctl enable --now mes-dashboard mes-dashboard-watchdog

# 5. 查看狀態
sudo systemctl status mes-dashboard
sudo systemctl status mes-dashboard-watchdog
```

執行 runtime contract 驗證：

```bash
RUNTIME_CONTRACT_ENFORCE=true ./scripts/start_server.sh check
```

### Rollback 步驟

如需回滾到先前版本：

```bash
# 1. 停止服務
./scripts/start_server.sh stop
sudo systemctl stop mes-dashboard mes-dashboard-watchdog

# 2. 回滾程式碼
git checkout <previous-commit>

# 3. 重新安裝依賴（如有變更）
pip install -r requirements.txt

# 4. 清理新版本資料（可選）
rm -f logs/admin_logs.sqlite  # 清理 SQLite 日誌

# 5. 重啟服務
./scripts/start_server.sh start
sudo systemctl start mes-dashboard mes-dashboard-watchdog
```

---

## 使用者操作指南

本節提供一般使用者的操作說明。

### 存取系統

1. 開啟瀏覽器，輸入系統網址（預設為 `http://localhost:8080`）
2. 進入 Portal 首頁，可透過上方 Tab 切換各功能模組

### 基本操作

#### WIP 即時概況
- 顯示生產線 WIP（在製品）的即時統計
- 可透過下拉選單篩選特定工作中心或產品線
- 點擊統計卡片可展開查看詳細明細
- 支援匯出 Excel 報表

#### WIP 明細查詢
1. 選擇篩選條件（工作中心、Package、Hold 狀態、製程站點）
2. 點擊「查詢」按鈕執行查詢
3. 查詢結果顯示於下方表格
4. 點擊「匯出 Excel」下載報表

#### 設備狀態監控
- 顯示所有設備的即時狀態（PRD/SBY/UDT/SDT/EGT/NST）
- 使用階層篩選功能：
  - **生產設備**：僅顯示列入生產統計的設備
  - **重點設備**：僅顯示標記為重點監控的設備
  - **監控設備**：僅顯示需特別監控的設備
- 設備狀態每 30 秒自動更新

#### 設備歷史查詢
1. 選擇查詢日期範圍
2. 可選擇特定設備或工作中心
3. 查看歷史趨勢圖表和稼動率熱力圖
4. 支援 CSV 匯出

### 管理員登入

1. 點擊右上角「登入」按鈕
2. 輸入工號和密碼（使用 LDAP 認證）
3. 登入後可存取開發中功能頁面
4. 管理員可使用效能監控儀表板（`/admin/performance`）

### 常見問題

**Q: 頁面顯示「資料載入中」很久沒反應？**
A: 請檢查網路連線，或重新整理頁面。如持續發生請通知系統管理員。

**Q: 查詢結果與預期不符？**
A: 請確認篩選條件是否正確設定。資料來源為 MES 系統，約有 30 秒延遲。

**Q: 無法匯出 Excel？**
A: 請確認瀏覽器允許下載檔案，並檢查查詢結果是否有資料。

---

## 功能說明

### Portal 入口頁面

透過側邊欄抽屜分組導覽切換各功能模組：
- **報表類**：WIP 即時概況、設備即時概況、設備歷史績效、QC-GATE 即時狀態
- **查詢類**：設備維修查詢、批次追蹤工具、TMTT 不良分析
- **開發工具**（admin only）：數據表查詢、Excel 批次查詢、頁面管理、效能監控
- 抽屜/頁面配置可由管理員動態管理（新增、重排、刪除）

### WIP 即時概況

- 總覽統計（Total Lots、Total QTY）+ 狀態卡片（RUN/QUEUE/品質異常/非品質異常）
- Workcenter × Package 矩陣表（Top 15 欄位、sticky 首欄、Total 行列）
- Hold Pareto 分析（品質/非品質分組、ECharts 雙軸柏拉圖 + 明細表）
- Autocomplete 篩選（WORKORDER/LOT ID/PACKAGE/TYPE，cross-filter + 300ms debounce）
- 矩陣點擊 drill-down 至 WIP Detail、Pareto 點擊 drill-down 至 Hold Detail
- 10 分鐘自動刷新 + AbortController 請求取消
- **技術架構**：Vue 3 + Vite，Pareto 圖使用 vue-echarts

### WIP 明細查詢

- 依工作中心顯示 LOT 明細（4 sticky 欄 + 動態 Spec 欄位）
- 狀態卡片篩選（RUN/QUEUE/品質異常/非品質異常）
- 點擊 LOT ID 展開 inline 詳細面板（基本/產品/製程/物料/Hold/NCR 資訊）
- Autocomplete 篩選（含 cross-filter）+ 伺服器端分頁
- URL params 接收 Overview drill-down 參數（workcenter + filters）
- 10 分鐘自動刷新 + AbortController 請求取消
- **技術架構**：Vue 3 + Vite

### Hold 狀態分析

- 依 Hold 原因顯示摘要統計（Total Lots/QTY/平均滯留/最久滯留/影響站群）
- 品質異常/非品質異常分類（前端常數判斷，紅/橙 gradient header）
- Age 分布卡片篩選（0-1天/1-3天/3-7天/7+天）
- Workcenter/Package 分布表篩選
- LOT 明細表（10 欄 + 伺服器端分頁 + 篩選指示器）
- 10 分鐘自動刷新 + AbortController 請求取消
- **技術架構**：Vue 3 + Vite，URL params 取代 Jinja2 注入

### 設備狀態監控

- 即時設備狀態總覽（PRD/SBY/UDT/SDT/EGT/NST）
- 按工作中心群組統計
- 設備稼動率（OU%）與運轉率（RUN%）
- 階層篩選（廠區/產線/重點設備/監控設備）
- Redis 快取自動更新（30 秒間隔）

### 設備歷史查詢

- 歷史狀態趨勢分析
- 稼動率熱力圖視覺化
- 設備狀態明細查詢
- 支援 CSV 匯出

### QC-GATE 即時狀態報表

- 顯示所有 QC-GATE 站點的 LOT 即時分佈（堆疊條圖）
- 等待時間四級分類：<6hr（綠）、6-12hr（黃）、12-24hr（橙）、>24hr（紅）
- 點擊條圖區段篩選下方 LOT 明細表
- 10 分鐘自動刷新，與 WIP 快取同步
- 站點排序依 DW_MES_SPEC_WORKCENTER_V 製程順序
- **技術架構**：第一個純 Vue 3 + Vite 頁面，完全脫離 Jinja2

### 數據表查詢工具

- 顯示所有 DWH 表格的分類卡片目錄（即時數據表/現況快照表/歷史累積表/輔助表）
- 大表標記：超過 1,000 萬筆資料的表格顯示 badge 提示
- 選擇表格後自動載入欄位資訊，每欄提供篩選輸入
- 支援 Enter 鍵或「查詢」按鈕觸發查詢（預設回傳最近 1000 筆）
- 使用中的篩選條件顯示為可移除的 tag，支援一鍵清除全部
- **技術架構**：第二個純 Vue 3 + Vite 頁面，使用 `apiPost` 建立 POST 請求模式

### 管理員功能

- LDAP 認證登入（支援本地測試模式）
- 頁面狀態管理（released/dev）
- 抽屜管理（新增、重命名、排序、刪除導覽分類）
- 頁面歸屬管理（指派頁面到抽屜、調整顯示順序）
- Dev 頁面僅管理員可見

### 效能監控儀表板

管理員專用的系統監控介面（`/admin/performance`）：

- **系統狀態總覽**：Database、Redis、Circuit Breaker、Worker 狀態
- **查詢效能指標**：P50/P95/P99 延遲、慢查詢統計、延遲分布圖
- **系統日誌檢視**：即時日誌查詢、等級篩選、關鍵字搜尋
- **日誌管理**：儲存統計、手動清理功能
- **Worker 控制**：優雅重啟（透過 Watchdog 機制）
- 自動更新（30 秒間隔）

### 熔斷器保護機制

Circuit Breaker 模式保護資料庫免於雪崩效應：

- **CLOSED**：正常運作，請求通過
- **OPEN**：失敗過多，請求立即拒絕
- **HALF_OPEN**：測試恢復，允許有限請求

配置方式：
```bash
CIRCUIT_BREAKER_ENABLED=true
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_FAILURE_RATE=0.5
CIRCUIT_BREAKER_RECOVERY_TIMEOUT=30
```

---

## 技術架構

### 後端技術棧

| 技術 | 版本 | 用途 |
|------|------|------|
| Python | 3.11+ | 程式語言 |
| Flask | 3.x | Web 框架 |
| Gunicorn | 23.x | WSGI 伺服器 |
| SQLAlchemy | 2.x | ORM |
| oracledb | 2.x | Oracle 驅動 |
| Redis | 7.x | 快取伺服器 |
| Pandas | 2.x | 資料處理 |

### 前端技術棧

| 技術 | 用途 |
|------|------|
| Jinja2 | 模板引擎（既有頁面） |
| Vue 3 | UI 框架（QC-GATE、Tables、WIP 三頁已遷移，漸進式擴展中） |
| vue-echarts | ECharts Vue 封裝（QC-GATE、WIP Overview Pareto 圖） |
| Vite 6 | 前端多頁模組打包（含 Vue SFC + HTML entry） |
| ECharts | 圖表庫（npm tree-shaking + 舊版靜態檔案並存） |
| Vanilla JS Modules | 互動功能與頁面邏輯（既有頁面） |

### 資料庫

- Oracle Database 19c Enterprise Edition
- 主機: 詳見 .env 檔案 (DB_HOST:DB_PORT)
- 服務名: 詳見 .env 檔案 (DB_SERVICE)

---

## 專案結構

```
DashBoard_vite/
├── src/mes_dashboard/          # 主程式
│   ├── app.py                  # Flask 應用
│   ├── config/                 # 設定
│   │   ├── settings.py         # 環境設定
│   │   ├── constants.py        # 常數定義
│   │   ├── field_contracts.py  # UI/API/Export 欄位契約
│   │   └── workcenter_groups.py # 工作中心群組設定
│   ├── core/                   # 核心模組
│   │   ├── database.py         # 資料庫連線
│   │   ├── redis_client.py     # Redis 客戶端
│   │   ├── cache.py            # 快取管理
│   │   ├── cache_updater.py    # 快取自動更新
│   │   ├── circuit_breaker.py  # 熔斷器
│   │   ├── metrics.py          # 效能指標收集
│   │   ├── log_store.py        # SQLite 日誌儲存
│   │   ├── response.py         # API 回應格式
│   │   └── permissions.py      # 權限管理
│   ├── routes/                 # 路由
│   │   ├── wip_routes.py       # WIP 相關 API
│   │   ├── resource_routes.py  # 設備狀態 API
│   │   ├── dashboard_routes.py # 儀表板 API
│   │   └── ...                 # 其他路由
│   ├── services/               # 服務層
│   │   ├── wip_service.py      # WIP 業務邏輯
│   │   ├── resource_service.py # 設備狀態邏輯
│   │   ├── resource_cache.py   # 設備快取服務
│   │   └── ...                 # 其他服務
│   ├── sql/                    # SQL 查詢管理
│   │   ├── loader.py           # SQLLoader (LRU 快取)
│   │   ├── builder.py          # QueryBuilder (參數化)
│   │   ├── filters.py          # CommonFilters
│   │   ├── dashboard/          # 儀表板查詢
│   │   ├── resource/           # 設備查詢
│   │   ├── wip/                # WIP 查詢
│   │   └── resource_history/   # 設備歷史查詢
│   └── templates/              # HTML 模板
├── frontend/                   # Vite 前端專案
│   ├── src/core/               # 共用 API/欄位契約/計算 helper
│   ├── src/portal/             # Portal entry
│   ├── src/resource-status/    # 設備即時概況 entry
│   ├── src/resource-history/   # 設備歷史績效 entry
│   ├── src/job-query/          # 設備維修查詢 entry
│   ├── src/excel-query/        # Excel 批次查詢 entry
│   ├── src/tables/             # 數據表查詢 entry (Vue 3 SFC)
│   ├── src/qc-gate/            # QC-GATE 即時狀態 (Vue 3 SFC)
│   ├── src/wip-shared/         # WIP 三頁共用 CSS/常數/元件
│   ├── src/wip-overview/       # WIP 即時概況 (Vue 3 SFC)
│   ├── src/wip-detail/         # WIP 明細查詢 (Vue 3 SFC)
│   └── src/hold-detail/        # Hold 狀態分析 (Vue 3 SFC)
├── shared/
│   └── field_contracts.json    # 前後端共用欄位契約
├── scripts/                    # 腳本
│   ├── deploy.sh               # 部署腳本
│   ├── start_server.sh         # 服務管理腳本
│   └── worker_watchdog.py      # Worker 監控程式
├── deploy/                     # 部署設定
│   ├── mes-dashboard.service            # Gunicorn systemd 服務 (Conda)
│   ├── mes-dashboard-watchdog.service   # Watchdog systemd 服務 (Conda)
├── tests/                      # 測試
├── data/                       # 資料檔案
├── logs/                       # 日誌
├── docs/                       # 文檔
├── openspec/                   # 變更管理
├── .env.example                # 環境變數範例
├── requirements.txt            # Python 依賴
└── gunicorn.conf.py            # Gunicorn 設定
```

---

## 測試

```bash
# 執行所有測試
pytest tests/ -v

# 執行單元測試
pytest tests/test_*.py -v --ignore=tests/e2e --ignore=tests/stress

# 執行整合測試
pytest tests/test_*_integration.py -v

# 執行 E2E 測試
pytest tests/e2e/ -v

# 執行壓力測試
pytest tests/stress/ -v

# Cache benchmark gate（P1）
conda run -n mes-dashboard python scripts/run_cache_benchmarks.py --enforce
```

---

## 故障排除

### 服務無法啟動

1. 檢查 Conda 環境：
   ```bash
   conda activate mes-dashboard
   ```

2. 檢查依賴：
   ```bash
   pip install -r requirements.txt
   ```

3. 檢查日誌：
   ```bash
   ./scripts/start_server.sh logs error
   ```

### 資料庫連線失敗

1. 確認 `.env` 中的資料庫設定正確
2. 確認網路可連線到資料庫伺服器
3. 確認資料庫帳號密碼正確

### Port 被占用

1. 檢查 port 使用狀況：
   ```bash
   lsof -i :8080
   ```

2. 修改 `.env` 中的 `GUNICORN_BIND` 設定

---

## 變更日誌

### 2026-02-09

- 完成 WIP 三頁 Vue 3 遷移（`/wip-overview`、`/wip-detail`、`/hold-detail`）：
  - 三頁共 1,941 行 vanilla JS + Jinja2 模板重寫為 Vue 3 SFC 元件架構
  - 抽取 `wip-shared/` 共用模組：CSS 基底（`:root` 變數、gradient header、responsive）、常數（`NON_QUALITY_HOLD_REASONS` 11 值）、Pagination/FilterBar 元件
  - Overview：Pareto 圖改用 vue-echarts（`<VChart autoresize>`），與 QC-GATE 一致
  - Hold Detail：Jinja2 模板注入（`reason`、`hold_type`）改為前端 URL params + 常數判斷
  - Hold Detail：新增 10 分鐘自動刷新 + `visibilitychange` 即時刷新 + AbortController
  - 三頁 Vite entry 從 `main.js` 改為 `index.html`，Flask route 改為 `send_from_directory`
  - 移除三份 Jinja2 模板（`wip_overview.html`、`wip_detail.html`、`hold_detail.html`）
- 完成數據表查詢頁面（`/tables`）Vue 3 遷移：
  - 237 行 vanilla JS + Jinja2 模板重寫為 Vue 3 SFC 元件（App.vue、TableCatalog.vue、DataViewer.vue）
  - Vite entry 從 `main.js` 改為 `index.html`，Flask route 改為 `send_from_directory`
  - 使用 `apiPost` 建立純 Vite 頁面 POST 請求模式
  - 移除 Jinja2 模板 `templates/index.html`，完全脫離 `window.MesApi` 依賴
- 修復設備即時概況（`/resource`）資料為空問題：
  - 根因：process-level DataFrame cache（30s TTL）過期後，derived index 仍標記 `ready: true`
  - `_records_from_index()` 取得 `df=None` 時直接回傳空 list
  - 修復：新增 `_get_cached_data()` fallback，從 Redis 重新載入 DataFrame
- 修正 `page_status.json` 設備頁面名稱：「機台狀態」→「設備即時概況」
- 新增 QC-GATE 即時狀態報表頁面（`/qc-gate`）：
  - 第一個純 Vue 3 + Vite 頁面，完全脫離 Jinja2 模板
  - ECharts 堆疊條圖顯示各 QC-GATE 站點 LOT 分佈（按 6hr 時間分級）
  - 點擊條圖篩選下方 LOT 明細表，支援排序與清除篩選
  - 10 分鐘自動刷新 + visibilitychange 即時刷新
  - 後端 API（`/api/qc-gate/summary`）從 WIP Redis 快取篩選，零額外 Oracle 查詢
  - 站點排序依 `DW_MES_SPEC_WORKCENTER_V` 的 `SPEC_ORDER`
- 前端架構升級：
  - 引入 Vue 3、`@vitejs/plugin-vue`、`echarts`（npm）、`vue-echarts`
  - Vite config 新增 Vue plugin、HTML entry point、`vendor-vue` chunk splitting
  - 建立純 Vite 頁面模式（Flask `send_from_directory` 服務靜態 HTML）
- 完成 Portal 動態抽屜導覽管理：
  - sidebar drawer/page 配置改為 JSON 動態管理
  - 管理員可 CRUD 抽屜、指派頁面歸屬與排序
  - 首次啟動自動 migration 建立預設抽屜結構
  - Gunicorn 多 worker mtime 快取一致性修復
- `filter_cache.py` 新增 `SPEC → SPEC_ORDER` mapping 快取

### 2026-02-08

- 完成並封存提案 `post-migration-resilience-governance`
- 完成並封存提案 `p1-cache-query-efficiency`
- 完成並封存提案 `p2-ops-self-healing-runbook`
- 新增 runtime 韌性診斷核心（thresholds / restart churn / recovery recommendation）
- 新增 worker restart policy state（allowed/cooldown/blocked）與 guarded mode override 流程
- health 與 admin API 新增可操作韌性欄位：
  - `/health`、`/health/deep`
  - `/admin/api/system-status`、`/admin/api/worker/status`
- watchdog restart state 支援 bounded history（`WATCHDOG_RESTART_HISTORY_MAX`）
- WIP overview/detail 抽離共用 autocomplete/filter 模組（`frontend/src/core/autocomplete.js`）
- WIP overview/detail 導入共享 derive 模組（`frontend/src/core/wip-derive.js`）
- 新增 cache benchmark fixture 與 baseline-vs-indexed 門檻驗證
- 新增前端 Node 測試流程（`npm --prefix frontend test`）
- 更新 `README.mdj` 與 migration runbook 文件對齊 gate

### 2026-02-07

- 完成並封存提案 `dashboard-vite-root-refactor`
- 完成並封存提案 `dashboard-vite-complete-migration`
- 完成並封存提案 `vite-jinja-report-parity-hardening`
- 完成並封存提案 `hold-detail-vite-hardening`
- 完成單一 port Vite 架構切換，根目錄成為唯一執行與部署主體
- 完成 portal 抽屜分類導航、獨立頁與 drill-down 路徑對齊
- 完成欄位契約治理與下載欄位一致性驗證
- 完成 runtime resilience（pool/circuit/degraded contract）與 migration gates/runbook 建立

### 2026-02-04

- 新增效能監控儀表板（`/admin/performance`）
- 新增熔斷器保護機制（Circuit Breaker）
- 新增效能指標收集（P50/P95/P99 延遲、慢查詢統計）
- 新增 SQLite 日誌儲存與管理功能
- 新增 Worker Watchdog 重啟機制
- 新增統一 API 回應格式（success_response/error_response）
- 新增 404/500 錯誤頁面模板
- 修復熔斷器 get_status() 死鎖問題
- 修復 health_routes.py 模組匯入錯誤
- 新增 psutil 依賴用於 Worker 狀態監控
- 新增完整測試套件（59 個效能相關測試）

### 2026-02-03

- 重構 SQL 查詢管理架構，提升安全性與效能
- 新增 SQLLoader (LRU 快取)、QueryBuilder (參數化)、CommonFilters 模組
- 抽取 20 個 SQL 檔案至 `src/mes_dashboard/sql/` 目錄
- 修復所有 SQL 注入風險（LIKE 萬用字元跳脫、IN 條件參數化）
- 優化 workcenter_cards API 回應時間（55s → 0.1s）

### 2026-02-02

- 新增 Hold Summary 柏拉圖視覺化圖表
- 設備頁面統一排序、階層篩選與標籤優化

### 2026-01-30

- 新增本地認證模式支援開發測試環境

### 2026-01-29

- 新增設備狀態監控頁面
- 新增設備歷史查詢頁面
- 整合 Redis 快取系統（30 秒自動更新）

### 2026-01-28

- 新增管理員認證系統（LDAP 整合）
- 新增頁面狀態管理（released/dev）
- 新增部署腳本 `deploy.sh`
- 更新啟動腳本自動載入 `.env`
- 新增完整測試套件（57 個測試）

### 2026-01-27

- 新增 Hold Detail 頁面
- WIP 查詢排除原物料
- Hold 狀態分類（品質異常/非品質異常）

### 2026-01-26

- 重構為 Flask App Factory 模式
- 新增全域連線管理
- 新增 WIP 篩選增強功能

---

## 聯絡方式

如有技術問題或需求變更，請聯繫系統管理員。

---

**文檔版本**: 5.2
**最後更新**: 2026-02-09
