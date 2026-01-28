# Deployment Configuration Enhancement

## Problem Statement

目前專案的環境變數設定不完整，缺少以下關鍵配置：
- `.env.example` 未包含所有必要的環境變數（如 SECRET_KEY、LDAP_API_URL、PORT 設定等）
- 啟動腳本 `start_server.sh` 未明確載入 `.env` 檔案
- 缺少生產環境部署的完整指引

這導致部署時需要手動設定多個環境變數，容易遺漏且不易維護。

## Proposed Solution

1. **更新 `.env.example`**：加入所有必要的環境變數及說明
2. **修改啟動腳本**：確保從 `.env` 檔案讀取環境變數
3. **建立部署腳本**：自動化部署流程（環境檢查、依賴安裝、服務啟動）

## Goals

- 所有環境變數集中在 `.env` 檔案管理
- 新部署只需複製 `.env.example`、填入值即可運行
- 啟動腳本自動載入 `.env` 檔案
- 提供 production-ready 的部署指引

## Non-Goals

- 不建立 Docker 容器化部署（可作為未來功能）
- 不建立 CI/CD 自動部署流程
- 不變更現有的 Gunicorn 配置邏輯

## Capabilities

1. **env-config**: 更新 `.env.example` 包含完整環境變數
2. **startup-script**: 修改啟動腳本載入 `.env` 檔案
3. **deploy-script**: 建立部署腳本自動化初始設定

## Impact

### Files to Modify
- `.env.example` - 新增缺少的環境變數
- `scripts/start_server.sh` - 加入 `.env` 載入邏輯

### Files to Create
- `scripts/deploy.sh` - 部署腳本

### Dependencies
- 無新增依賴（`python-dotenv` 已在 requirements.txt）

## Success Criteria

- [ ] `.env.example` 包含所有環境變數並有清楚註解
- [ ] `start_server.sh` 啟動時自動載入 `.env`
- [ ] 新機器可透過 `deploy.sh` 完成部署
- [ ] 現有服務重啟後正常運作
