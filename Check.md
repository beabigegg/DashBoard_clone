# MES Dashboard 報表系統 專案健康度審查報告

> 審查日期：2026-04-15
> 審查人員：Claude Code (claude-sonnet-4-6)
> 審查版本：main branch (`3d2626c`)
> 整體評估：**CONDITIONAL PASS**
> 通過項目：20 / 21（不含 N/A）
> 專案功能：半導體製造廠 MES 數據自助報表平台，提供 16 個報表頁面、AI 查詢助手與異常偵測

---

## 專案概述

本系統為全端 Web 應用，供半導體製造廠各部門工程師自助查詢 MES 生產數據。後端採 Flask + Gunicorn + RQ，前端為 Vue 3 + Vite 多頁應用，同源單一 Port 部署。資料庫唯讀存取 Oracle 19c，並以 Redis + DuckDB 多層快取加速查詢，搭配熔斷器、記憶體守護、異步任務佇列等韌性機制。

---

## 審查結果

| # | 項目 | 狀態 | 說明 |
|---|------|------|------|
| 1-1 | 資料夾結構 | PASS | routes / services / core / config / sql / templates / frontend/src 分層清晰；tests / scripts / deploy / contract 完整 |
| 1-2 | 主程式入口 | PASS | 後端：`src/mes_dashboard/app.py`（`create_app()`）；前端：`frontend/src/portal-shell/main.js` |
| 2-1 | 依賴檔存在 | PASS | `requirements.txt`（Python）+ `frontend/package.json`（Node） |
| 2-2 | 依賴檔品質 | PASS | requirements.txt 有分區塊 `#` 註解、bounded 版本區間，固定版本有附說明理由 |
| 2-4 | 前端版本鎖定 | PASS | `^` 版本搭配 `package-lock.json`；deploy.sh 使用 `npm ci`（嚴格鎖版） |
| 2-3 | 禁止套件 | PASS | 所有套件均為活躍維護的主流開源專案，無已知高風險 CVE |
| 3-1 | 環境變數檔案 | PASS | `.env.example` 完整（481 行），`.env` 已列入 `.gitignore`，機敏資訊全透過 `os.getenv()` 讀取 |
| 3-2 | 環境變數完整性 | WARN | PORT：`GUNICORN_BIND=0.0.0.0:8080`（嵌入格式，非獨立 `PORT`）；`CORS_ALLOWED_ORIGINS` 定義於 `.env.example` 但 app.py 未使用（同源架構實際不需要） |
| 3-3 | 環境區分 | PASS | `DevelopmentConfig` / `ProductionConfig` / `TestingConfig` 三組設定；`FLASK_ENV` 控制載入 |
| 4-1 | 錯誤處理 | PASS | 全域 7 個 error handler；統一回應格式（`core/response.py`）；16 個路由檔 138 個 try 區塊 |
| 4-2 | 註解 | PASS | 核心模組有 docstring；`.env.example` 詳細中英文說明；契約文件完整 |
| 4-3 | 硬編碼敏感資訊 | PASS | 所有機敏資訊（DB 密碼、SECRET_KEY、AI Key）均從環境變數讀取，無硬編碼 |
| 4-4 | 安全防護 | PASS | SQL 參數化（Oracle bind variables）；CSP / XSS / CSRF / HSTS / HttpOnly Cookie 全套 |
| 4-5 | Log 規範 | PASS | 89 個檔案使用 `logging.getLogger()`，零 `print()`；`SecretRedactionFilter` 過濾機敏資訊 |
| 5-1 | .gitignore 存在 | PASS | 根目錄 `.gitignore`（94 行）+ `frontend/.gitignore` |
| 5-2 | .gitignore 排除項 | PASS | `.env` / `__pycache__` / `node_modules` / `dist` / `*.log` / `tmp` / `nul` / IDE / OS 全部涵蓋 |
| 6-1 | 必要文件 | PASS | README.md / PRD.md / SDD.md / TDD.md 均已存在（相較上次審查：三份文件已補齊） |
| 6-2 | README 完整性 | PASS | 含專案介紹、技術架構、安裝方式、環境變數說明、啟動指令、使用方式、部署說明 |
| 6-3 | API 健康檢查 | PASS | `/health`、`/health/deep`、`/health/frontend-shell` 端點；`openspec/openapi.yaml` OpenAPI 文件 |
| 7-1 | 權限檢查 | PASS | `@login_required` + `@admin_required` 裝飾器；admin 路由 23 處套用 |
| 7-2 | 未驗證存取 | PASS | 全域 `before_request` 中介層：`/api/` 要求登入、`/admin/` 要求管理員，未驗證一律擋下 |

---

## 關鍵問題（FAIL 項目）

本次審查無 FAIL 項目。

---

## 改善建議（非必要但建議）

| 優先級 | 項目 | 說明 |
|--------|------|------|
| ⚠️ 低 | 3-2 CORS 變數清理 | `.env.example` 定義的 `CORS_ALLOWED_ORIGINS` 在程式碼中未被讀取。同源架構不需要 CORS，建議移除或加上「目前不使用」的說明，避免維運誤解 |
| ⚠️ 低 | 3-2 PORT 格式 | `PORT` 嵌入於 `GUNICORN_BIND=0.0.0.0:8080`，與獨立 `PORT` 變數的慣例有差異。實務影響低，可視需要額外加 `PORT=8080` 供參考 |
| ℹ️ 備忘 | `scrap_reason_exclusion_cache.py` 本機 fix 未提交 | 2026-04-15 部署修復的循環遞迴 bug（`refresh_cache ↔ get_excluded_reasons` 互相呼叫）尚未 commit 至遠端，建議適時推上 |
| ℹ️ 備忘 | DuckDB f-string SQL | `material_trace_duckdb_runtime.py`、`anomaly_detection_sql_runtime.py` 等使用 f-string 建構 DuckDB SQL，操作對象為內部 Parquet 路徑（非使用者輸入），風險可控 |

---

## 版本歷程

| 審查日期 | 版本 Commit | 整體評估 | 主要變動 |
|----------|-------------|----------|----------|
| 2026-04-01 | `b2218a4` | CONDITIONAL PASS | 初版審查；PRD/SDD/TDD 三份文件缺失為主要問題 |
| 2026-04-15 | `3d2626c` | CONDITIONAL PASS | PRD/SDD/TDD 已全部補齊；新增 spool null schema 修復；循環遞迴 bug（scrap_reason_exclusion_cache）本機已修未 commit |
