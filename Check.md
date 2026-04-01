# 專案健檢報告
**專案名稱**：MES Dashboard 報表系統
**健檢日期**：2026-04-01

## 專案技術架構
| 項目 | 技術 |
|------|------|
| **前端** | Vue 3.5 + Vite 6.3 + Tailwind CSS 3.4 + ECharts 6.0 + DuckDB-WASM 1.33 |
| **後端** | Python 3.11 + Flask 3.x + Gunicorn 21.x + SQLAlchemy 2.x + Redis 5.x + RQ 1.16 |
| **資料庫** | Oracle Database 19c Enterprise Edition + Redis 7.x（快取）+ SQLite（日誌/session）|

## 專案啟動指令
```bash
# 啟動服務
./scripts/start_server.sh start

# 停止服務
./scripts/start_server.sh stop

# 建置前端
npm --prefix frontend install
npm --prefix frontend run build

# 執行測試
pytest tests/ -v
```

---

## 1. 專案結構

### 1-1 具備可辨識、可預期的資料夾結構 🟢 完全符合

專案採用清晰的分層架構：
- `src/mes_dashboard/routes/` — 路由層（20 個 Blueprint）
- `src/mes_dashboard/services/` — 服務層（45+ 模組）
- `src/mes_dashboard/core/` — 核心基礎設施（28+ 模組）
- `src/mes_dashboard/config/` — 設定模組
- `src/mes_dashboard/sql/` — SQL 查詢模板（85+ 檔案）
- `src/mes_dashboard/templates/` — HTML 模板
- `frontend/src/` — Vue 3 前端（19 個 entry point）
- `tests/` — 後端測試（127+ 檔案）
- `frontend/tests/` — 前端測試（32+ 檔案）
- `scripts/` — 部署與維運腳本
- `deploy/` — systemd 服務設定
- `contract/` — 開發契約文件

### 1-2 具有單一且明確的主程式入口檔案 🟢 完全符合

- 後端入口：`src/mes_dashboard/app.py` — Flask 應用工廠 `create_app()`
- 開發模式入口：`src/mes_dashboard/__main__.py`（`python -m mes_dashboard`）
- 前端入口：`frontend/src/portal-shell/main.js`（SPA 主路由）
- 各報表頁面各有獨立 `main.js` 入口（Vite MPA 架構）

---

## 2. 相依套件

### 2-1 具備依賴檔 🟢 完全符合

- Python：`requirements.txt`（根目錄）
- Node.js：`frontend/package.json`

### 2-2 依賴檔格式是否清楚且可維護 🟢 完全符合

- `requirements.txt` 具備完整的 `#` 註解說明每個套件用途（如 `# Core Framework`、`# Database`、`# Data Processing` 等區塊）
- 版本策略明確：採用有界區間（`>=x.y.z,<N.0.0`），檔案開頭說明策略並建議產生 lock file
- 需要固定版本的套件有附理由（如 `pandas==2.3.3` 註明「pandas 3.x removed DBAPI2 flow」）
- `package.json` 使用 `^` 語義化版本控制，符合 npm 慣例

### 2-3 未使用禁止套件 🟢 完全符合

- 所有 Python 套件均為活躍維護的主流開源專案（Flask、SQLAlchemy、pandas、redis、rq 等）
- 所有前端套件均為活躍維護的主流開源專案（Vue 3、Vite、ECharts、Tailwind CSS 等）
- 未發現已停止維護或來源不明的套件

---

## 3. 環境設定

### 3-1 具備環境變數檔案，且所有機敏資料皆來自環境變數 🟢 完全符合

- 提供完整的 `.env.example`（479 行），涵蓋所有設定項目且附詳細註解
- `.env` 已列入 `.gitignore`（第 39 行），不會被提交至版本控制
- 所有機敏資料（DB 密碼、SECRET_KEY、AI API Key、LDAP URL、MySQL 密碼）均透過 `os.getenv()` 讀取
- `src/mes_dashboard/config/settings.py` 提供型別安全的環境變數讀取輔助函式（`_int_env`、`_bool_env`、`_float_env`、`_csv_env`）

### 3-2 環境變數是否包含必要資訊 🟡 部分符合

- **服務監聽 Port**：⚠ `GUNICORN_BIND=0.0.0.0:8080` 存在於 `.env.example`，但非獨立的 `PORT` 變數，而是嵌入在 bind 地址中
- **DB 連線資訊**：✅ 完整（`DB_HOST`、`DB_PORT`、`DB_SERVICE`、`DB_USER`、`DB_PASSWORD`）
- **CORS 來源**：⚠ `.env.example` 中 `CORS_ALLOWED_ORIGINS=`（空值），且程式碼中（`app.py`）完全未找到 CORS 處理邏輯（無 `Access-Control` header 設定、無 flask-cors 套件）。因為本專案採單一 Port 同源架構（前後端由同一 Gunicorn 服務提供），CORS 在實務上非必要，但 `.env.example` 中定義了此變數卻未被程式使用
- **Debug 模式**：✅ `FLASK_DEBUG=0`，且 `settings.py` 中 `ProductionConfig.DEBUG = False`

### 3-3 條件式資訊 🟢 完全符合

- **API Key / Token**：✅ `AI_API_KEY` 透過環境變數設定（`.env.example:453`）
- **SECRET_KEY**：✅ 透過環境變數設定，且正式環境若缺失或使用不安全預設值會啟動失敗（`app.py:217-233` `_resolve_secret_key`）
- **JWT_SECRET**：🟤 專案使用 Flask session（非 JWT），不適用
- **OAuth**：🟤 專案使用 LDAP 驗證，非 OAuth 機制，不適用

### 3-4 區分 dev / prod 設定 🟢 完全符合

- `src/mes_dashboard/config/settings.py` 定義三組設定類別：
  - `Config`（基底，第 37 行）
  - `DevelopmentConfig(Config)`（開發，第 103 行）
  - `ProductionConfig(Config)`（正式，第 125 行）
- 透過 `FLASK_ENV` 環境變數選擇載入哪個設定
- `.env.example` 在資源配置區塊以註解清楚標示 DEV/PRD 參數差異

---

## 4. 程式內容

### 4-1 具備完整的錯誤處理機制 🟢 完全符合

- **全域錯誤處理**：`app.py:1205-1294`（`_register_error_handlers`）註冊 401/403/404/500/DatabasePoolExhaustedError/DatabaseCircuitOpenError/Exception 共 7 個全域錯誤處理器
- **統一回應格式**：`core/response.py` 提供 10+ 個標準化回應輔助函式（`success_response`、`validation_error`、`not_found_error`、`db_connection_error` 等）
- **路由層錯誤處理**：16 個路由檔案中共有 138 個 `try` 區塊
- **熔斷器**：`core/circuit_breaker.py` 防止資料庫雪崩
- **頻率限制**：`core/rate_limit.py` 保護高成本 API

### 4-2 關鍵程式邏輯具備清楚的註解說明 🟢 完全符合

- 核心模組均有模組級 docstring 說明用途
- `core/response.py` 開頭有完整的 Helper 使用指南表格
- `health_routes.py` 開頭有 CONTRACT EXCEPTION 說明為何不使用統一回應格式
- `config/settings.py` 各設定項有行內註解
- `.env.example` 每個區塊有詳細的中文/英文註解說明

### 4-3 不存在硬編碼的敏感資訊 🟢 完全符合

- 所有敏感資訊（DB 密碼、SECRET_KEY、API Key、LDAP URL、MySQL 密碼）均從環境變數讀取
- `settings.py` 中 `AI_API_URL` 有預設值但非機敏資訊（僅為 API endpoint URL）
- 未在 Python 原始碼中發現硬編碼的密碼或 token

### 4-4 具備基本的安全防護機制 🟢 完全符合

- **SQL Injection 防護**：
  - `sql/builder.py` 使用 Oracle bind variables（`:param_name`）進行參數化查詢
  - `core/database.py:981` 使用正規表達式 `_TABLE_NAME_PATTERN` 驗證表名格式
  - `core/database.py:993-996` 對 `table_name` 進行白名單驗證
  - SQL 模板檔案（`sql/` 目錄 85+ 檔案）使用參數化查詢
  - 注意：部分 DuckDB runtime 使用 f-string 建構 SQL（如 `services/material_trace_duckdb_runtime.py:94`、`services/anomaly_detection_sql_runtime.py` 多處），但這些操作對象為本地 Parquet 檔案路徑（非使用者輸入），風險可控
- **XSS 防護**：
  - 全域安全標頭：CSP（`app.py:126-146`）、X-Content-Type-Options: nosniff、X-Frame-Options: SAMEORIGIN
  - Session Cookie 設定 HttpOnly=True（`app.py:539`）、SameSite=Strict（正式環境，`app.py:541`）
- **CSRF 防護**：`core/csrf.py` + `app.py:643-663` 的 `enforce_csrf` before_request 中介層
- **HSTS**：正式環境 HTTPS 請求自動加上 `Strict-Transport-Security`（`app.py:670-672`）

### 4-5 Log 記錄符合規範 🟢 完全符合

- **正式 logging 機制**：89 個檔案使用 `logging.getLogger()`（共 101 次呼叫），未發現任何 `print()` 呼叫
- **Log 敏感資訊保護**：`core/database.py:83` 的 `install_log_redaction_filter()` 安裝 `SecretRedactionFilter`，自動過濾 log 中的敏感資訊
- **Log 層級管理**：`app.py:88-90` 根據 debug 模式設定 INFO/DEBUG 層級
- **Log 持久化**：SQLite log handler 將 INFO+ 級別日誌寫入 SQLite 供管理儀表板查詢

---

## 5. Git 安全規範

### 5-1 具備 .gitignore 檔案 🟢 完全符合

根目錄 `.gitignore`（83 行）+ `frontend/.gitignore`（3 行）

### 5-2 .gitignore 必須包含排除項目 🟢 完全符合

| 排除項目 | 狀態 | 對應規則 |
|----------|------|----------|
| 環境變數 `.env` | ✅ | 第 39 行 |
| `node_modules` | ✅ | 第 20 行 `frontend/node_modules/` |
| `__pycache__` | ✅ | 第 2 行 |
| 編譯產物 `dist/`、`build/` | ✅ | 第 17-18 行 |
| Log 檔 `*.log` | ✅ | 第 36 行 |
| 上傳/暫存目錄 `tmp/` | ✅ | 第 58 行 |
| `reports/` | ✅ | 第 59 行 |
| Windows 誤建檔案 `nul` | ✅ | 第 32 行 |
| IDE 檔案 `.idea/`、`.vscode/` | ✅ | 第 23-24 行 |
| OS 檔案 `.DS_Store`、`Thumbs.db` | ✅ | 第 30-31 行 |
| 虛擬環境 `venv/` 等 | ✅ | 第 9-12 行 |
| 測試產物 `.pytest_cache/` 等 | ✅ | 第 49-51 行 |

---

## 6. 文件與維運可用性

### 6-1 必須具有下述檔案及內容 🟡 部分符合

| 文件 | 狀態 | 說明 |
|------|------|------|
| **README.md** | ✅ 存在 | 內容完整（詳見 6-2） |
| **PRD.md** | ❌ 不存在 | 專案根目錄及子目錄均未找到此檔案 |
| **SDD.md** | ❌ 不存在 | 專案根目錄及子目錄均未找到此檔案 |
| **TDD.md** | ❌ 不存在 | 專案根目錄及子目錄均未找到此檔案 |

### 6-2 README.md 是否完整 🟢 完全符合

| 必要內容 | 狀態 | 位置 |
|----------|------|------|
| 專案介紹 | ✅ | 第 1-8 行（專案名稱、技術棧、架構簡述） |
| 系統架構簡述 | ✅ | 第 60-96 行（後端/前端技術棧表格）+ 第 254-313 行（8 大架構重點） |
| 安裝方式 | ✅ | 第 317-334 行（首次部署步驟） |
| 環境變數說明 | ✅ | 第 94 行指向 `.env` 檔案 + `.env.example` 本身有 479 行詳細說明 |
| 啟動指令 | ✅ | 第 317-334 行（首次部署）+ 日常操作指令 |
| 佈署說明 | ✅ | 第 317-334 行 + `deploy/` 目錄含 systemd 服務設定 + `scripts/deploy.sh` |

### 6-3 API 類型專案檢查 🟤 未使用

本專案為一般 Web 應用程式（具備完整的前端畫面與 Portal Shell SPA），內部 API 供自身前端使用，非以 API 為主要交付介面的 API 類型專案。不過值得一提的是，專案實際上具備 `/health` 和 `/health/deep` 健康檢查端點（`src/mes_dashboard/routes/health_routes.py`），以及完整的 API 清冊（`contract/api_inventory.md`）。

---

## 7. 權限與存取控制

### 7-1 API 或功能是否具備基本權限檢查（admin / user） 🟢 完全符合

- `core/permissions.py` 提供兩個權限裝飾器：
  - `@login_required`（第 50 行）— 要求任何已登入使用者
  - `@admin_required`（第 60 行）— 要求管理員身份
- Admin 路由大量使用 `@admin_required`（`routes/admin_routes.py` 中 23 處）
- `routes/user_auth_routes.py:215` 使用 `@login_required`

### 7-2 是否避免未驗證使用者存取受保護資源 🟢 完全符合

- **全域 before_request 中介層**（`app.py:604-641`）：
  - 所有 `/api/` 路徑（非 public API）要求使用者已登入，否則回傳 401
  - 所有 `/admin/` 路徑要求管理員身份，否則重導至登入頁
  - 狀態為 `dev` 的頁面僅管理員可存取
  - `/health` 端點、認證端點、靜態檔案豁免驗證
- **CSRF 保護中介層**（`app.py:643-663`）：admin form 與 mutation API 強制 CSRF token 驗證

---

## 8. 其他明顯安全疑慮

### 8-1 CORS 變數已定義但未被使用 🟡 部分符合

`.env.example:102` 定義了 `CORS_ALLOWED_ORIGINS` 變數，但程式碼中（`app.py` 及所有路由檔案）完全未找到 CORS 相關處理邏輯（無 `Access-Control` header 設定、未安裝 `flask-cors` 套件）。由於專案採單一 Port 同源架構，前後端由同一服務提供，CORS 在實務上非必要。但建議移除 `.env.example` 中未使用的 `CORS_ALLOWED_ORIGINS` 設定項，避免誤導維運人員。

### 8-2 DuckDB f-string SQL 語句 🟡 部分符合

多個 DuckDB runtime 檔案使用 f-string 建構 SQL（對本地 Parquet 檔案操作），例如：
- `services/material_trace_duckdb_runtime.py:94,103,142,158`
- `services/anomaly_detection_sql_runtime.py:190,301,411,619,758,827,893,970`
- `core/database.py:975`（`get_table_columns` 中的 `table_name`，但有 regex 白名單保護）
- `core/cache_updater.py:207`

這些 f-string 的值來源為內部常數或已驗證的檔案路徑（非使用者直接輸入），風險較低，但不符合最嚴格的參數化查詢標準。

---

## 健檢總結

| 評估結果 | 項目 |
|------|----------|
| 🟢 完全符合 | 1-1 具備可辨識、可預期的資料夾結構 |
| 🟢 完全符合 | 1-2 具有單一且明確的主程式入口檔案 |
| 🟢 完全符合 | 2-1 具備依賴檔 |
| 🟢 完全符合 | 2-2 依賴檔格式是否清楚且可維護 |
| 🟢 完全符合 | 2-3 未使用禁止套件 |
| 🟢 完全符合 | 3-1 具備環境變數檔案，且所有機敏資料皆來自環境變數 |
| 🟡 部分符合 | 3-2 環境變數是否包含必要資訊 |
| 🟢 完全符合 | 3-3 條件式資訊 |
| 🟢 完全符合 | 3-4 區分 dev / prod 設定 |
| 🟢 完全符合 | 4-1 具備完整的錯誤處理機制 |
| 🟢 完全符合 | 4-2 關鍵程式邏輯具備清楚的註解說明 |
| 🟢 完全符合 | 4-3 不存在硬編碼的敏感資訊 |
| 🟢 完全符合 | 4-4 具備基本的安全防護機制 |
| 🟢 完全符合 | 4-5 Log 記錄符合規範 |
| 🟢 完全符合 | 5-1 具備 .gitignore 檔案 |
| 🟢 完全符合 | 5-2 .gitignore 包含必要排除項目 |
| 🟡 部分符合 | 6-1 必須具有指定文件（README/PRD/SDD/TDD） |
| 🟢 完全符合 | 6-2 README.md 是否完整 |
| 🟤 未使用 | 6-3 API 類型專案檢查 |
| 🟢 完全符合 | 7-1 API 或功能具備基本權限檢查 |
| 🟢 完全符合 | 7-2 避免未驗證使用者存取受保護資源 |
| 🟡 部分符合 | 8 其他明顯安全疑慮 |

🟢 完全符合 18 項
🟡 部分符合 3 項
🔴 不符合 0 項
🟤 未使用 1 項

### 優先改善項目
1. **[中]** 缺少 PRD.md、SDD.md、TDD.md 三份文件。專案已有豐富的 `contract/` 目錄與 `openspec/` 變更規格，但缺少標準化的產品需求文件、系統設計文件與測試設計文件。
2. **[低]** `.env.example` 中定義了 `CORS_ALLOWED_ORIGINS` 變數但程式碼中未使用，建議移除以避免維運誤解。
3. **[低]** 部分 DuckDB runtime 使用 f-string 建構 SQL 語句，雖然操作對象為內部 Parquet 檔案路徑（非使用者輸入），風險可控，但可考慮統一使用參數化方式以符合最嚴格標準。
