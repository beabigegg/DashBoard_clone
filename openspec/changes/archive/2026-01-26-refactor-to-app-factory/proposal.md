## Why

目前的 Flask 應用直接在 module level 建立 `app = Flask(...)`，並使用 `sys.path.insert` hacks 處理 import。這種架構無法支援多 worker 部署、測試困難，且不符合 Flask 最佳實踐。公司報表系統需要支援多人使用，架構必須具備未來擴充性。

## What Changes

- 重構為 Application Factory pattern (`create_app()`)
- 建立正式 Python package 結構，移除所有 `sys.path.insert` hacks
- 新增 WSGI 部署設定 (Gunicorn)
- 建立 Cache 抽象層（目前為 no-op 實作，保留未來擴充介面）
- 統一 config 管理，支援多環境設定
- **BREAKING**: 應用啟動方式改變，從 `python portal.py` 改為使用 gunicorn 或 `flask run`

## Capabilities

### New Capabilities

- `app-factory`: Application Factory pattern 實作，支援建立可配置的 Flask app instance
- `package-structure`: 正式 Python package 結構，使用標準 import 機制
- `deployment-config`: WSGI 部署設定，包含 gunicorn 配置與啟動腳本

### Modified Capabilities

<!-- 目前無既有 specs，此為全新建立 -->

## Impact

- **Code**:
  - `apps/` 目錄重構為 `src/mes_dashboard/`
  - 所有現有模組 import 路徑改變
  - `portal.py` 拆分為 `app.py` (factory) + entry point
- **啟動方式**:
  - 開發: `flask run` 或 `python -m mes_dashboard`
  - 生產: `gunicorn "mes_dashboard:create_app()"`
- **Dependencies**: 新增 gunicorn、python-dotenv（如尚未有）
- **現有功能**: 所有 routes、services、templates 保持不變，僅調整 import 路徑
