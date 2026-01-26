## 1. Package 結構建立

- [x] 1.1 建立 `pyproject.toml` 定義 package metadata 和 dependencies
- [x] 1.2 建立 `src/mes_dashboard/` 目錄結構
- [x] 1.3 建立所有 `__init__.py` 檔案

## 2. Config 模組遷移

- [x] 2.1 建立 `src/mes_dashboard/config/settings.py` - Config classes (Base, Dev, Prod)
- [x] 2.2 遷移 `apps/config/database.py` → `src/mes_dashboard/config/database.py`
- [x] 2.3 遷移 `apps/config/constants.py` → `src/mes_dashboard/config/constants.py`
- [x] 2.4 遷移 `apps/config/workcenter_groups.py` → `src/mes_dashboard/config/workcenter_groups.py`
- [x] 2.5 建立 `src/mes_dashboard/config/tables.py` 從 database.py 分離 TABLES_CONFIG

## 3. Core 模組遷移

- [x] 3.1 建立 `src/mes_dashboard/core/database.py` - Engine factory + request-scoped get_db()
- [x] 3.2 建立 `src/mes_dashboard/core/cache.py` - CacheBackend protocol + NoOpCache
- [x] 3.3 遷移 `apps/core/utils.py` → `src/mes_dashboard/core/utils.py`

## 4. Services 模組遷移

- [x] 4.1 遷移 `apps/services/wip_service.py` - 更新 import paths
- [x] 4.2 遷移 `apps/services/resource_service.py` - 更新 import paths
- [x] 4.3 遷移 `apps/services/dashboard_service.py` - 更新 import paths
- [x] 4.4 遷移 `apps/services/excel_query_service.py` - 更新 import paths

## 5. Routes 模組遷移

- [x] 5.1 遷移 `apps/routes/wip_routes.py` - 更新 import paths，移除 cache 呼叫
- [x] 5.2 遷移 `apps/routes/resource_routes.py` - 更新 import paths
- [x] 5.3 遷移 `apps/routes/dashboard_routes.py` - 更新 import paths
- [x] 5.4 遷移 `apps/routes/excel_query_routes.py` - 更新 import paths
- [x] 5.5 建立 `src/mes_dashboard/routes/__init__.py` - register_routes() function

## 6. Templates 遷移

- [x] 6.1 複製 `apps/templates/` → `src/mes_dashboard/templates/`

## 7. Application Factory

- [x] 7.1 建立 `src/mes_dashboard/app.py` - create_app() factory function
- [x] 7.2 建立 `src/mes_dashboard/__main__.py` - development entry point

## 8. 部署設定

- [x] 8.1 建立 `gunicorn.conf.py` - Gunicorn 配置
- [x] 8.2 建立 `scripts/start_server.sh` - Linux 啟動腳本
- [x] 8.3 更新 `scripts/啟動Dashboard.bat` - Windows 啟動腳本

## 9. 清理與驗證

- [x] 9.1 執行 `pip install -e .` 驗證 package 安裝
- [x] 9.2 啟動應用驗證所有頁面和 API
- [x] 9.3 移除舊的 `apps/` 目錄
- [x] 9.4 更新 `.gitignore` 加入 egg-info 等
