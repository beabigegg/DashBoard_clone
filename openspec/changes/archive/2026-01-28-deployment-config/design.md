# Deployment Configuration - Technical Design

## Overview

本設計涵蓋三個部分：環境變數配置、啟動腳本修改、部署腳本建立。

## 1. Environment Configuration (env-config)

### 完整環境變數清單

根據 `settings.py`、`gunicorn.conf.py` 和 `auth_service.py` 分析，需要以下環境變數：

```bash
# ============================================================
# Database Configuration
# ============================================================
DB_HOST=10.1.1.58
DB_PORT=1521
DB_SERVICE=DWDB
DB_USER=your_username
DB_PASSWORD=your_password

# Database Pool Settings (optional)
DB_POOL_SIZE=5          # Default: 5 (dev: 2, prod: 10)
DB_MAX_OVERFLOW=10      # Default: 10 (dev: 3, prod: 20)

# ============================================================
# Flask Configuration
# ============================================================
FLASK_ENV=development   # development | production | testing
FLASK_DEBUG=0           # 0 for production, 1 for development

# Session Security (REQUIRED for production)
SECRET_KEY=your-secret-key-change-in-production

# Session timeout in seconds (default: 28800 = 8 hours)
SESSION_LIFETIME=28800

# ============================================================
# Authentication Configuration
# ============================================================
LDAP_API_URL=https://adapi.panjit.com.tw
ADMIN_EMAILS=ymirliu@panjit.com.tw

# ============================================================
# Gunicorn Configuration
# ============================================================
GUNICORN_BIND=0.0.0.0:8080
GUNICORN_WORKERS=2      # Recommend: 2 * CPU cores + 1
GUNICORN_THREADS=4      # Threads per worker
```

### 變數分類

| Category | Required | Variables |
|----------|----------|-----------|
| Database | Yes | DB_HOST, DB_PORT, DB_SERVICE, DB_USER, DB_PASSWORD |
| Flask | Yes | FLASK_ENV, SECRET_KEY |
| Auth | No (has defaults) | LDAP_API_URL, ADMIN_EMAILS |
| Gunicorn | No (has defaults) | GUNICORN_BIND, GUNICORN_WORKERS, GUNICORN_THREADS |
| Tuning | No (has defaults) | DB_POOL_SIZE, DB_MAX_OVERFLOW, SESSION_LIFETIME |

## 2. Startup Script Modification (startup-script)

### 修改位置

`scripts/start_server.sh` 的 `do_start()` 函數中。

### 實作方式

在啟動 gunicorn 之前，加入 `.env` 檔案載入：

```bash
# Load .env file if exists
load_env() {
    if [ -f "${ROOT}/.env" ]; then
        log_info "Loading environment from .env"
        set -a  # Mark all variables for export
        source "${ROOT}/.env"
        set +a
    fi
}
```

### 調用位置

在 `do_start()` 函數中，`conda activate` 之後、`gunicorn` 啟動之前：

```bash
do_start() {
    # ... existing checks ...

    conda activate "$CONDA_ENV"
    load_env  # <-- Add here
    export PYTHONPATH="${ROOT}/src:${PYTHONPATH:-}"

    # ... gunicorn startup ...
}
```

### 注意事項

- 使用 `set -a` / `set +a` 確保變數被 export
- `.env` 檔案不存在時不報錯（開發環境可能直接使用 shell 變數）
- 不覆蓋已設定的環境變數（優先順序：shell > .env）

## 3. Deployment Script (deploy-script)

### 功能需求

1. 檢查 Python/Conda 環境
2. 建立 Conda 環境（如不存在）
3. 安裝依賴
4. 複製 `.env.example` 到 `.env`（如不存在）
5. 提示使用者編輯 `.env`
6. 驗證資料庫連線
7. 啟動服務

### 腳本結構

```bash
#!/usr/bin/env bash
# scripts/deploy.sh - MES Dashboard Deployment Script

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONDA_ENV="mes-dashboard"
PYTHON_VERSION="3.11"

# Functions:
# - check_prerequisites()  - Check conda, git
# - setup_conda_env()      - Create/update conda environment
# - install_dependencies() - pip install -r requirements.txt
# - setup_env_file()       - Copy .env.example if needed
# - verify_database()      - Test database connection
# - show_next_steps()      - Print post-deployment instructions

main() {
    check_prerequisites
    setup_conda_env
    install_dependencies
    setup_env_file
    verify_database
    show_next_steps
}
```

### 互動流程

```
$ ./scripts/deploy.sh

[INFO] MES Dashboard Deployment
[INFO] Checking prerequisites...
[OK] Conda found
[OK] Git found

[INFO] Setting up conda environment...
[OK] Environment 'mes-dashboard' ready

[INFO] Installing dependencies...
[OK] Dependencies installed

[INFO] Setting up configuration...
[WARN] .env file not found
[INFO] Copying .env.example to .env
[IMPORTANT] Please edit .env with your database credentials:
    nano /path/to/.env

[INFO] Press Enter after editing .env to continue...

[INFO] Verifying database connection...
[OK] Database connection successful

========================================
  Deployment Complete!
========================================

Start the server:
  ./scripts/start_server.sh start

View logs:
  ./scripts/start_server.sh logs follow

Access URL:
  http://localhost:8080
```

## File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `.env.example` | Modify | Add all environment variables with documentation |
| `scripts/start_server.sh` | Modify | Add `load_env()` function |
| `scripts/deploy.sh` | Create | New deployment automation script |

## Rollback Plan

此變更為向後相容：
- 現有 `.env` 檔案不受影響
- 環境變數有預設值，不會因缺少新變數而失敗
- `start_server.sh` 即使沒有 `.env` 也能正常運作
