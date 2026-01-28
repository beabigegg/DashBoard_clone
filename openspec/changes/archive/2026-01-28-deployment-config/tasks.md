# Deployment Configuration 實作任務

## Task 1: 更新 .env.example

- [x] 加入 Database Configuration 區塊（DB_HOST, DB_PORT, DB_SERVICE, DB_USER, DB_PASSWORD）
- [x] 加入 Database Pool Settings 區塊（DB_POOL_SIZE, DB_MAX_OVERFLOW）
- [x] 加入 Flask Configuration 區塊（FLASK_ENV, FLASK_DEBUG, SECRET_KEY, SESSION_LIFETIME）
- [x] 加入 Authentication Configuration 區塊（LDAP_API_URL, ADMIN_EMAILS）
- [x] 加入 Gunicorn Configuration 區塊（GUNICORN_BIND, GUNICORN_WORKERS, GUNICORN_THREADS）
- [x] 每個變數加入說明註解

## Task 2: 修改 start_server.sh

- [x] 新增 `load_env()` 函數
- [x] 在 `do_start()` 中呼叫 `load_env()`（conda activate 之後）
- [x] 測試：設定 `.env` 中的 `GUNICORN_BIND=0.0.0.0:9000`，確認服務監聽 9000 port

## Task 3: 建立 deploy.sh

- [x] 建立 `scripts/deploy.sh` 腳本
- [x] 實作 `check_prerequisites()` - 檢查 conda
- [x] 實作 `setup_conda_env()` - 建立/更新 conda 環境
- [x] 實作 `install_dependencies()` - pip install requirements.txt
- [x] 實作 `setup_env_file()` - 複製 .env.example 並提示編輯
- [x] 實作 `verify_database()` - 測試資料庫連線
- [x] 實作 `show_next_steps()` - 顯示後續步驟
- [x] 設定執行權限 `chmod +x scripts/deploy.sh`

## Task 4: 驗證與測試

- [x] 在新環境測試 `deploy.sh` 完整流程（手動驗證）
- [x] 確認 `start_server.sh` 正確載入 `.env`（手動驗證）
- [x] 確認現有 `.env` 的服務重啟正常（手動驗證）
- [x] 確認 SECRET_KEY 變更後 session 仍正常運作（手動驗證）
