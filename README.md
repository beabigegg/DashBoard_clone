# MES Dashboard 報表系統

基於 Flask + Gunicorn + Redis 的 MES 數據報表查詢與可視化系統

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
| 部署自動化 | ✅ 已完成 |

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
# 啟動服務（背景執行）
./scripts/start_server.sh start

# 停止服務
./scripts/start_server.sh stop

# 重啟服務
./scripts/start_server.sh restart

# 查看狀態
./scripts/start_server.sh status

# 查看日誌
./scripts/start_server.sh logs follow
```

訪問網址: **http://localhost:8080** （可在 .env 中配置）

---

## 部署指南

### 環境需求

- Python 3.11+
- Conda (Miniconda/Anaconda)
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

# Redis 設定
REDIS_HOST=localhost          # Redis 伺服器位址
REDIS_PORT=6379               # Redis 端口
REDIS_DB=0                    # Redis 資料庫編號

# 管理員設定
ADMIN_EMAILS=admin@example.com # 管理員郵件（逗號分隔）
```

### 生產環境注意事項

1. **SECRET_KEY**: 必須設定為隨機字串
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

2. **FLASK_ENV**: 設定為 `production`

3. **防火牆**: 開放服務端口（預設 8080）

### Worker Watchdog 服務配置

Watchdog 監控程式用於支援管理員從介面優雅重啟 Workers：

```bash
# 1. 複製 systemd 服務檔案
sudo cp deploy/mes-dashboard-watchdog.service /etc/systemd/system/

# 2. 編輯服務檔案，修改路徑和用戶
sudo nano /etc/systemd/system/mes-dashboard-watchdog.service

# 3. 重新載入 systemd
sudo systemctl daemon-reload

# 4. 啟動並設定開機自動啟動
sudo systemctl start mes-dashboard-watchdog
sudo systemctl enable mes-dashboard-watchdog

# 5. 查看狀態
sudo systemctl status mes-dashboard-watchdog
```

### Rollback 步驟

如需回滾到先前版本：

```bash
# 1. 停止服務
./scripts/start_server.sh stop
sudo systemctl stop mes-dashboard-watchdog

# 2. 回滾程式碼
git checkout <previous-commit>

# 3. 重新安裝依賴（如有變更）
pip install -r requirements.txt

# 4. 清理新版本資料（可選）
rm -f logs/admin_logs.sqlite  # 清理 SQLite 日誌

# 5. 重啟服務
./scripts/start_server.sh start
sudo systemctl start mes-dashboard-watchdog
```

---

## 功能說明

### Portal 入口頁面

透過 Tab 切換各功能模組：
- WIP 即時概況
- WIP 明細查詢
- Hold 狀態分析
- 設備狀態監控
- 設備歷史查詢
- 數據表查詢工具

### WIP 即時概況

- 總覽統計（總 LOT 數、總數量、總片數）
- 按 SPEC 和 WORKCENTER 統計
- 按產品線統計（匯總 + 明細）
- Hold 狀態分類（品質異常/非品質異常）
- 柏拉圖視覺化圖表

### WIP 明細查詢

- 依工作中心篩選
- 依 Package 篩選
- 依 Hold 狀態篩選
- 依製程站點篩選
- 支援 Excel 匯出

### Hold 狀態分析

- Hold 批次總覽
- 按 Hold 原因分類
- Hold 明細查詢
- 品質異常分類統計

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

### 管理員功能

- LDAP 認證登入（支援本地測試模式）
- 頁面狀態管理（released/dev）
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
| Jinja2 | 模板引擎 |
| Bootstrap 5 | UI 框架 |
| Chart.js | 圖表庫 |
| Vanilla JS | 互動功能 |

### 資料庫

- Oracle Database 19c Enterprise Edition
- 主機: 詳見 .env 檔案 (DB_HOST:DB_PORT)
- 服務名: 詳見 .env 檔案 (DB_SERVICE)

---

## 專案結構

```
DashBoard/
├── src/mes_dashboard/          # 主程式
│   ├── app.py                  # Flask 應用
│   ├── config/                 # 設定
│   │   ├── settings.py         # 環境設定
│   │   ├── constants.py        # 常數定義
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
├── scripts/                    # 腳本
│   ├── deploy.sh               # 部署腳本
│   ├── start_server.sh         # 服務管理腳本
│   └── worker_watchdog.py      # Worker 監控程式
├── deploy/                     # 部署設定
│   └── mes-dashboard-watchdog.service  # Watchdog systemd 服務
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

**文檔版本**: 4.0
**最後更新**: 2026-02-04
